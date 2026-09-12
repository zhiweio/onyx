export async function captureObjectUrlExport(
  trigger: () => void | Promise<void>
): Promise<Uint8Array> {
  const createObjectURL = URL.createObjectURL.bind(URL);
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      URL.createObjectURL = createObjectURL;
      reject(new Error("Export timed out"));
    }, 20_000);

    URL.createObjectURL = (object: Blob | MediaSource) => {
      const url = createObjectURL(object);
      if (object instanceof Blob) {
        void object
          .arrayBuffer()
          .then((buffer) => {
            window.clearTimeout(timeout);
            URL.createObjectURL = createObjectURL;
            resolve(new Uint8Array(buffer));
          })
          .catch((error: unknown) => {
            window.clearTimeout(timeout);
            URL.createObjectURL = createObjectURL;
            reject(error);
          });
      }
      return url;
    };

    void Promise.resolve(trigger()).catch((error: unknown) => {
      window.clearTimeout(timeout);
      URL.createObjectURL = createObjectURL;
      reject(error);
    });
  });
}
