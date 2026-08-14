// jsdom не умеет читать `Blob` — без полифилла multipart-запрос не доезжает
// до обработчика вовсе (см. сам модуль).
import "@/test/blob-polyfill";

import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { getApiErrorMessage } from "@/shared/lib/api-error";
import { server } from "@/test/msw/server";

import { uploadFile } from "./uploads";

// Integration: транспорт вложений (feat-011, T2.7). Файл уезжает в `uploads/`
// проекта одним multipart-запросом, а обратно приезжает канонический путь —
// именно он потом кладётся в тело `POST /messages` (design-brief § Вложения
// пользователя). Сеть — MSW.

const UPLOADS_URL = "/api/projects/p1/uploads";

function textFile(name = "notes.md"): File {
  return new File(["конспект"], name, { type: "text/markdown" });
}

describe("uploadFile", () => {
  it("отправляет файл multipart-запросом и возвращает серверный путь, а не имя исходного файла", async () => {
    // Имя файла и путь ответа намеренно расходятся: бэкенд санитайзит имя и
    // разводит коллизии числовым суффиксом (design-brief § Вложения
    // пользователя), поэтому путь, собранный на фронте из `file.name`, сослался
    // бы на несуществующий файл — и этот ассерт он не прошёл бы.
    let body = "";
    let contentType: string | null = null;
    server.use(
      http.post(UPLOADS_URL, async ({ request }) => {
        contentType = request.headers.get("content-type");
        body = await request.text();
        return HttpResponse.json({ path: "uploads/lecture-2.pdf" });
      }),
    );

    const result = await uploadFile("p1", textFile("lecture.pdf"));

    expect(result).toEqual({ path: "uploads/lecture-2.pdf" });
    // Поле формы называется `file` — по нему бэкенд и читает вложение;
    // содержимое и имя уезжают вместе с ним.
    expect(body).toContain('name="file"');
    expect(body).toContain('filename="lecture.pdf"');
    expect(body).toContain("конспект");
    // Boundary выставляет сам транспорт: заголовок, прописанный руками, ушёл бы
    // без него, и сервер не разобрал бы тело.
    expect(contentType).toContain("multipart/form-data");
    expect(contentType).toContain("boundary=");
  });

  it("превышение лимита размера доезжает читаемым текстом сервера", async () => {
    // A14: лимит знает только сервер (предпроверки на клиенте нет), поэтому
    // текст ошибки композера — это `detail` его ответа, а не своя формулировка.
    server.use(
      http.post(UPLOADS_URL, () =>
        HttpResponse.json(
          { detail: "Файл больше 20 МБ — уменьшите его и попробуйте снова" },
          { status: 413 },
        ),
      ),
    );

    const failure = await uploadFile("p1", textFile()).then(
      () => null,
      (err: unknown) => err,
    );

    expect(failure).not.toBeNull();
    expect(getApiErrorMessage(failure)).toBe(
      "Файл больше 20 МБ — уменьшите его и попробуйте снова",
    );
  });
});
