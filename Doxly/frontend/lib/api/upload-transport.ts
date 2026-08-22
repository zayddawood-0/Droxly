/**
 * The direct-to-storage PUT (specs/architecture.md §4) — this is the one
 * upload-path call that does NOT go through apiFetch/the BFF proxy, by
 * design: the browser uploads straight to object storage using the
 * presigned URL, never through our own backend. Uses XMLHttpRequest rather
 * than fetch() specifically because fetch has no cross-browser-reliable
 * upload-progress event; XHR's `upload.onprogress` is what drives the
 * per-file progress bar (ui-ux.md §6).
 */
export function putFileWithProgress(
  url: string,
  file: File,
  headers: Record<string, string>,
  onProgress: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url, true);
    for (const [key, value] of Object.entries(headers)) {
      xhr.setRequestHeader(key, value);
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.onabort = () => reject(new Error("Upload cancelled"));

    xhr.send(file);
  });
}
