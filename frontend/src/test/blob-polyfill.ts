// Local test helper (not part of the frozen harness). jsdom's `Blob` implements
// neither `arrayBuffer()`, nor `text()`, nor `stream()`, and the request
// interceptor MSW puts under XHR needs at least one of them to read a body that
// carries a file. Without them a `multipart/form-data` upload never finishes:
// the request hangs until the test times out, with no error to explain why.
// Importing this module installs minimal implementations on top of `FileReader`
// (which jsdom does implement), so any test that exercises a file upload can
// see the request reach the handler.
//
// Границы помощи. Тело доезжает до обработчика целиком и читается как текст
// (`await request.text()` — имя поля, имя файла и содержимое на месте), а вот
// `request.formData()` отдаёт часть-файл объектом чужого realm: `instanceof
// File` на нём ложен. Проверять форму тела поэтому надёжнее по сырому
// multipart-тексту.

function readAsBuffer(blob: Blob): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as ArrayBuffer);
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(blob);
  });
}

const blobProto = Blob.prototype as unknown as Record<string, unknown>;

if (typeof blobProto.arrayBuffer !== "function") {
  blobProto.arrayBuffer = function (this: Blob): Promise<ArrayBuffer> {
    return readAsBuffer(this);
  };
}

if (typeof blobProto.text !== "function") {
  blobProto.text = async function (this: Blob): Promise<string> {
    return new TextDecoder().decode(await readAsBuffer(this));
  };
}

function blobStream(blob: Blob): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      controller.enqueue(new Uint8Array(await readAsBuffer(blob)));
      controller.close();
    },
  });
}

if (typeof blobProto.stream !== "function") {
  blobProto.stream = function (this: Blob): ReadableStream<Uint8Array> {
    return blobStream(this);
  };
}
