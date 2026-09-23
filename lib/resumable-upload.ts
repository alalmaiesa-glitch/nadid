"use client";

import * as tus from "tus-js-client";

type ResumableUploadInput = {
  file: File;
  storagePath: string;
  signedToken: string;
  onProgress?: (percentage: number) => void;
};

function directStorageEndpoint() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!url) throw new Error("supabase_url_missing");

  const parsed = new URL(url);
  const projectRef = parsed.hostname.split(".")[0];

  if (!projectRef) throw new Error("supabase_project_ref_missing");

  return `https://${projectRef}.storage.supabase.co/storage/v1/upload/resumable`;
}

export function uploadResumable({
  file,
  storagePath,
  signedToken,
  onProgress
}: ResumableUploadInput) {
  return new Promise<void>((resolve, reject) => {
    const upload = new tus.Upload(file, {
      endpoint: directStorageEndpoint(),
      retryDelays: [0, 3000, 5000, 10000, 20000],
      headers: {
        "x-signature": signedToken
      },
      uploadDataDuringCreation: true,
      removeFingerprintOnSuccess: true,
      chunkSize: 6 * 1024 * 1024,
      metadata: {
        bucketName: "nadid-documents",
        objectName: storagePath,
        contentType:
          file.type ||
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        cacheControl: "3600"
      },
      onError(error) {
        reject(error);
      },
      onProgress(bytesUploaded, bytesTotal) {
        const percentage =
          bytesTotal > 0
            ? Math.round((bytesUploaded / bytesTotal) * 100)
            : 0;

        onProgress?.(percentage);
      },
      onSuccess() {
        resolve();
      }
    });

    upload
      .findPreviousUploads()
      .then((previousUploads) => {
        if (previousUploads.length > 0) {
          upload.resumeFromPreviousUpload(previousUploads[0]);
        }

        upload.start();
      })
      .catch(reject);
  });
}
