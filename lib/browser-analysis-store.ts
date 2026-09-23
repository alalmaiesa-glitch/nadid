"use client";

import type { AnalyzeResponse } from "@/lib/nadid-types";

const DB_NAME = "nadid-local";
const STORE_NAME = "analyses";
const DB_VERSION = 1;

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: "document.id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function saveAnalysis(data: AnalyzeResponse) {
  const db = await openDatabase();

  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(data);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });

  db.close();
}

export async function getAnalysis(documentId: string) {
  const db = await openDatabase();

  const result = await new Promise<AnalyzeResponse | undefined>(
    (resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, "readonly");
      const request = transaction.objectStore(STORE_NAME).get(documentId);

      request.onsuccess = () =>
        resolve(request.result as AnalyzeResponse | undefined);
      request.onerror = () => reject(request.error);
    }
  );

  db.close();
  return result;
}
