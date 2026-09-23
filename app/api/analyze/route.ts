import { randomUUID } from "node:crypto";
import mammoth from "mammoth";
import type {
  AnalyzeResponse,
  DocumentBlock,
  ProtectedFact,
  QuickSuggestion
} from "@/lib/nadid-types";
import { persistAnalyzedDocument } from "@/lib/server/document-persistence";
import {
  analyzeDocxWithAee,
  isAeeBackendConfigured
} from "@/lib/server/aee-client";

export const runtime = "nodejs";

const MAX_FILE_BYTES = 25 * 1024 * 1024;

function normalizeArabic(text: string) {
  return text
    .replace(/\u00a0/g, " ")
    .replace(/[\t ]+/g, " ")
    .replace(/\r/g, "")
    .trim();
}

function isLikelyHeading(text: string, index: number) {
  if (!text) return false;
  if (text.length > 90) return false;

  const headingWords =
    /^(الفصل|الباب|المبحث|المطلب|المقدمة|الخاتمة|التمهيد|الملخص|النتائج|التوصيات|المراجع)\b/;

  if (headingWords.test(text)) return true;
  if (index === 0 && text.split(/\s+/).length <= 12) return true;

  return false;
}

function buildBlocks(rawText: string): DocumentBlock[] {
  const pieces = rawText
    .split(/\n{2,}/)
    .map((part) => normalizeArabic(part))
    .filter(Boolean);

  return pieces.map((text, index) => ({
    id: `block_${index + 1}`,
    type: isLikelyHeading(text, index) ? "heading" : "paragraph",
    text
  }));
}

function suggestion(
  blockId: string,
  category: QuickSuggestion["category"],
  title: string,
  explanation: string,
  original: string,
  replacement: string | undefined,
  confidence: number
): QuickSuggestion {
  return {
    id: randomUUID(),
    blockId,
    category,
    title,
    explanation,
    original,
    replacement,
    confidence
  };
}

function quickReview(blocks: DocumentBlock[]): QuickSuggestion[] {
  const results: QuickSuggestion[] = [];

  for (const block of blocks) {
    const text = block.text;
    if (block.type !== "paragraph") continue;

    const punctuationSpace = text.match(/\s+([،؛:؟!,.])/);
    if (punctuationSpace) {
      const original = punctuationSpace[0];
      results.push(
        suggestion(
          block.id,
          "language",
          "مسافة قبل علامة ترقيم",
          "في العربية لا توضع مسافة قبل علامة الترقيم.",
          original,
          punctuationSpace[1],
          0.99
        )
      );
    }

    if (text.includes("تحسين من مستوى")) {
      results.push(
        suggestion(
          block.id,
          "style",
          "حرف جر زائد",
          "يمكن حذف «من» لتصبح العبارة أخف وأدق.",
          "تحسين من مستوى",
          "تحسين مستوى",
          0.97
        )
      );
    }

    if (/\bبناءاً\b/.test(text)) {
      results.push(
        suggestion(
          block.id,
          "language",
          "رسم إملائي",
          "الصواب في هذا الاستعمال «بناءً» دون ألف بعد الهمزة.",
          "بناءاً",
          "بناءً",
          0.99
        )
      );
    }

    if (/\bان شاء الله\b/.test(text)) {
      results.push(
        suggestion(
          block.id,
          "language",
          "فصل كلمتين",
          "الصواب «إن شاء الله»؛ لأن «إن» أداة شرط و«شاء» فعل.",
          "ان شاء الله",
          "إن شاء الله",
          0.98
        )
      );
    }

    const repeated = text.match(/\b([\u0600-\u06FF]{3,})\s+\1\b/u);
    if (repeated) {
      results.push(
        suggestion(
          block.id,
          "style",
          "تكرار كلمة",
          "وردت الكلمة نفسها مرتين متتاليتين.",
          repeated[0],
          repeated[1],
          0.94
        )
      );
    }
  }

  return results.slice(0, 80);
}

function extractProtectedFacts(blocks: DocumentBlock[]): ProtectedFact[] {
  const facts: ProtectedFact[] = [];
  const seen = new Set<string>();

  const push = (
    blockId: string,
    type: ProtectedFact["type"],
    value: string
  ) => {
    const key = `${blockId}:${type}:${value}`;
    if (seen.has(key)) return;
    seen.add(key);
    facts.push({
      id: randomUUID(),
      blockId,
      type,
      value
    });
  };

  for (const block of blocks) {
    const text = block.text;

    for (const match of text.matchAll(
      /\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\s*(?:ريال|ر\.س)?/g
    )) {
      const value = match[0].trim();
      push(
        block.id,
        /ريال|ر\.س/.test(value) ? "currency" : "number",
        value
      );
    }

    for (const match of text.matchAll(/\b\d+(?:\.\d+)?\s*%/g)) {
      push(block.id, "percentage", match[0]);
    }

    for (const match of text.matchAll(/\b(?:19|20)\d{2}\b/g)) {
      push(block.id, "date", match[0]);
    }

    for (const match of text.matchAll(
      /\bISO\s*\d{3,6}(?::\d{4})?\b/gi
    )) {
      push(block.id, "standard", match[0]);
    }

    for (const match of text.matchAll(
      /(?:^|\s)(?:و|ف)?(?:لا|لم|لن|ليس|ليست)\s+[^،؛.!؟\n]{1,55}/g
    )) {
      push(block.id, "negation", match[0].trim());
    }
  }

  return facts.slice(0, 200);
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const value = formData.get("file");

  if (!(value instanceof File)) {
    return Response.json(
      { error: "لم يتم إرسال ملف." },
      { status: 400 }
    );
  }

  if (!value.name.toLowerCase().endsWith(".docx")) {
    return Response.json(
      { error: "النسخة الحالية تقبل ملفات DOCX فقط." },
      { status: 415 }
    );
  }

  if (value.size > MAX_FILE_BYTES) {
    return Response.json(
      { error: "حجم الملف يتجاوز الحد التجريبي الحالي وهو 25 ميجابايت." },
      { status: 413 }
    );
  }

  try {
    const buffer = Buffer.from(await value.arrayBuffer());
    let aeeFallbackWarning = "";

    if (isAeeBackendConfigured()) {
      try {
        const response = await analyzeDocxWithAee(value.name, buffer);

        try {
          await persistAnalyzedDocument(response, buffer);
        } catch {
          response.warnings.push(
            "اكتمل تحليل AEE، لكن تعذر حفظ المستند في التخزين الدائم."
          );
        }

        return Response.json(response);
      } catch {
        aeeFallbackWarning =
          "تعذر الوصول إلى محرك AEE؛ استُخدم الفحص المحلي السريع كمسار احتياطي.";
      }
    }

    const extraction = await mammoth.extractRawText({ buffer });
    const blocks = buildBlocks(extraction.value);

    if (blocks.length === 0) {
      return Response.json(
        { error: "لم نتمكن من استخراج نص من المستند." },
        { status: 422 }
      );
    }

    const text = blocks.map((block) => block.text).join(" ");
    const wordCount = text.split(/\s+/).filter(Boolean).length;

    const response: AnalyzeResponse = {
      document: {
        id: randomUUID(),
        filename: value.name,
        wordCount,
        paragraphCount: blocks.filter(
          (block) => block.type === "paragraph"
        ).length,
        blocks
      },
      suggestions: quickReview(blocks),
      protectedFacts: extractProtectedFacts(blocks),
      warnings: [
        ...extraction.messages.map((message) => message.message),
        ...(aeeFallbackWarning ? [aeeFallbackWarning] : [])
      ]
    };

    try {
      const persistence = await persistAnalyzedDocument(response, buffer);
      if (!persistence.persisted) {
        response.warnings.push(
          "يعمل نَضِيد حاليًا بوضع التخزين المحلي لأن قاعدة البيانات لم تُربط بعد."
        );
      }
    } catch {
      response.warnings.push(
        "تم تحليل المستند بنجاح، لكن تعذر حفظه في التخزين الدائم؛ احتفظنا بالنتيجة محليًا في هذا المتصفح."
      );
    }

    return Response.json(response);
  } catch {
    return Response.json(
      { error: "تعذر قراءة ملف Word. تأكد من أن الملف سليم وغير مشفر." },
      { status: 422 }
    );
  }
}
