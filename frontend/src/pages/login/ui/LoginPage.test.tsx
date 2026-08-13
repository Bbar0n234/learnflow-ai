import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getAccessToken } from "@/shared/api/client";
import { logger } from "@/shared/lib/logger";
import { authProvidersHandlers } from "@/test/msw/auth-providers";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { LoginPage } from "./LoginPage";

// Integration (feat-008, трек T2): страница `/login` целиком — парольные режимы,
// блок кнопок провайдеров по составу с бэкенда и реестр кодов `?error=`.
// Контракт — design-brief § Целевой UX / § Эндпоинты (таблица кодов) и мокап
// feat-013 (копирайт, порядок Яндекс → Google → GitHub). Сеть — MSW
// (`onUnhandledRequest: "error"`), так что незаявленный запрос валит прогон:
// именно этим проверяется, что клик по провайдеру уходит в полную навигацию,
// а не в XHR. Маршрутизация наблюдается через MemoryRouter, чьи соседние роуты
// — маркеры «куда нас вернули».

const LOGIN_URL = "/api/auth/login";
const REGISTER_URL = "/api/auth/register";

const HOME_MARKER = "Домашний экран";
const PROJECT_MARKER = "Экран проекта";

const ACCESS_TOKEN = "header.payload.signature";

const NAME_FIELD = "Имя пользователя";
const PASSWORD_FIELD = "Пароль";
const CONFIRM_FIELD = "Повторите пароль";

const YANDEX_BUTTON = "Войти с Яндекс ID";
const GOOGLE_BUTTON = "Войти через Google";
const GITHUB_BUTTON = "Войти через GitHub";
const SEPARATOR = "или";

type Entry =
  | string
  | {
      pathname: string;
      search?: string;
      hash?: string;
      state?: { from: string };
    };

const ROUTES = (
  <Routes>
    <Route path="/login" element={<LoginPage />} />
    <Route path="/" element={<div>{HOME_MARKER}</div>} />
    <Route path="/projects/:id" element={<div>{PROJECT_MARKER}</div>} />
  </Routes>
);

function renderLoginAt(entry: Entry = "/login") {
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>{ROUTES}</MemoryRouter>,
  );
}

const BACK_LABEL = "Назад";

/** Кнопка «Назад» — заменитель браузерной кнопки в MemoryRouter. */
function BackButton() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => void navigate(-1)}>
      {BACK_LABEL}
    </button>
  );
}

/**
 * Рендер с предысторией: до `/login` в стеке лежит ещё одна запись, поэтому
 * шаг назад после входа наблюдаем — он показывает, заменил ли переход запись
 * `/login` в истории или задвинул её под новый экран.
 */
function renderLoginWithHistory(entry: Entry) {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/", entry]} initialIndex={1}>
      {ROUTES}
      <BackButton />
    </MemoryRouter>,
  );
}

function tokenResponse() {
  return HttpResponse.json({
    access_token: ACCESS_TOKEN,
    token_type: "bearer",
  });
}

async function fillCredentials(
  user: ReturnType<typeof userEvent.setup>,
  { name = "vasya", password = "secret123" } = {},
) {
  await user.type(screen.getByLabelText(NAME_FIELD), name);
  await user.type(screen.getByLabelText(PASSWORD_FIELD), password);
}

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
  // Спай на `logger.error` иначе переживает свой кейс и глушит логгер до конца
  // файла (`restoreMocks` в vitest.config.ts не включён) — порядок-зависимое
  // общее состояние.
  vi.restoreAllMocks();
});

describe("LoginPage — парольные режимы", () => {
  it("показывает каркас входа: заголовок, поля, кнопку и переход к регистрации", async () => {
    server.use(authProvidersHandlers.ru());

    renderLoginAt();

    expect(screen.getByRole("heading", { name: "Вход" })).toBeInTheDocument();
    expect(screen.getByLabelText(NAME_FIELD)).toBeInTheDocument();
    expect(screen.getByLabelText(PASSWORD_FIELD)).toBeInTheDocument();
    expect(screen.queryByLabelText(CONFIRM_FIELD)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    ).toBeInTheDocument();
  });

  it("переключается в регистрацию: повтор пароля, свои заголовок и кнопка", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru());

    renderLoginAt();
    await user.click(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    );

    expect(
      screen.getByRole("heading", { name: "Регистрация" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(CONFIRM_FIELD)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Зарегистрироваться" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Уже есть аккаунт? Войти" }),
    ).toBeInTheDocument();
  });

  it("держит кнопку отправки выключенной, пока имя и пароль не заполнены", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru());

    renderLoginAt();

    expect(screen.getByRole("button", { name: "Войти" })).toBeDisabled();
    await user.type(screen.getByLabelText(NAME_FIELD), "vasya");
    expect(screen.getByRole("button", { name: "Войти" })).toBeDisabled();
    await user.type(screen.getByLabelText(PASSWORD_FIELD), "secret123");
    expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
  });

  it("отклоняет регистрацию с паролем короче 8 символов, не дойдя до сервера", async () => {
    const user = userEvent.setup();
    const registerCalls = vi.fn();
    server.use(
      authProvidersHandlers.ru(),
      http.post(REGISTER_URL, () => {
        registerCalls();
        return tokenResponse();
      }),
    );

    renderLoginAt();
    await user.click(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    );
    await fillCredentials(user, { password: "short7" });
    await user.type(screen.getByLabelText(CONFIRM_FIELD), "short7");
    await user.click(
      screen.getByRole("button", { name: "Зарегистрироваться" }),
    );

    expect(
      await screen.findByText("Пароль должен содержать не менее 8 символов"),
    ).toBeInTheDocument();
    expect(registerCalls).not.toHaveBeenCalled();
    expect(getAccessToken()).toBeNull();
  });

  it("отклоняет регистрацию, когда повтор пароля не совпадает", async () => {
    const user = userEvent.setup();
    const registerCalls = vi.fn();
    server.use(
      authProvidersHandlers.ru(),
      http.post(REGISTER_URL, () => {
        registerCalls();
        return tokenResponse();
      }),
    );

    renderLoginAt();
    await user.click(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    );
    await fillCredentials(user);
    await user.type(screen.getByLabelText(CONFIRM_FIELD), "secret124");
    await user.click(
      screen.getByRole("button", { name: "Зарегистрироваться" }),
    );

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(registerCalls).not.toHaveBeenCalled();
  });

  it("регистрирует пользователя с обрезанными пробелами в имени", async () => {
    const user = userEvent.setup();
    let submittedName: unknown = null;
    server.use(
      authProvidersHandlers.ru(),
      http.post(REGISTER_URL, async ({ request }) => {
        const body = (await request.json()) as { name: string };
        submittedName = body.name;
        return tokenResponse();
      }),
    );

    renderLoginAt();
    await user.click(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    );
    await fillCredentials(user, { name: "  vasya  " });
    await user.type(screen.getByLabelText(CONFIRM_FIELD), "secret123");
    await user.click(
      screen.getByRole("button", { name: "Зарегистрироваться" }),
    );

    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
    expect(submittedName).toBe("vasya");
    expect(getAccessToken()).toBe(ACCESS_TOKEN);
  });

  it("после входа сохраняет access-токен и возвращает на путь, запомненный guard'ом", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru(), http.post(LOGIN_URL, tokenResponse));

    renderLoginAt({ pathname: "/login", state: { from: "/projects/p1" } });
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByText(PROJECT_MARKER)).toBeInTheDocument();
    expect(getAccessToken()).toBe(ACCESS_TOKEN);
  });

  it("после входа с прямого захода на /login отправляет на главную", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru(), http.post(LOGIN_URL, tokenResponse));

    renderLoginAt();
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
  });

  it("не даёт отправить форму дважды, пока запрос входа в полёте", async () => {
    const user = userEvent.setup();
    const loginCalls = vi.fn();
    server.use(
      authProvidersHandlers.ru(),
      http.post(LOGIN_URL, async () => {
        loginCalls();
        await delay(100);
        return tokenResponse();
      }),
    );

    renderLoginAt();
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    // Пока запрос в полёте, кнопка подписана «…» и выключена — второй клик по
    // ней не порождает второго запроса на критпути auth.
    const submitting = await screen.findByRole("button", { name: "…" });
    expect(submitting).toBeDisabled();
    await user.click(submitting);

    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
    expect(loginCalls).toHaveBeenCalledTimes(1);
  });

  it("после входа заменяет /login в истории: шаг назад не возвращает к форме", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru(), http.post(LOGIN_URL, tokenResponse));

    renderLoginWithHistory({
      pathname: "/login",
      state: { from: "/projects/p1" },
    });
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(PROJECT_MARKER)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: BACK_LABEL }));

    // Назад — на страницу до входа, а не на уже пройденный `/login`.
    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Вход" }),
    ).not.toBeInTheDocument();
  });

  it("показывает сообщение сервера при отказе входа и оставляет на странице", async () => {
    const user = userEvent.setup();
    // Отказ входа — штатная ветка контейнера, он пишет её в logger.error;
    // спай только глушит вывод, поведение проверяется по экрану.
    vi.spyOn(logger, "error").mockImplementation(() => {});
    server.use(
      authProvidersHandlers.ru(),
      http.post(LOGIN_URL, () =>
        HttpResponse.json(
          { detail: "Неверное имя или пароль" },
          { status: 401 },
        ),
      ),
    );

    renderLoginAt({ pathname: "/login", state: { from: "/projects/p1" } });
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(
      await screen.findByText("Неверное имя или пароль"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Вход" })).toBeInTheDocument();
    expect(screen.queryByText(PROJECT_MARKER)).not.toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
  });
});

describe("LoginPage — кнопки провайдеров", () => {
  it("рендерит все три кнопки, когда бэкенд отдаёт три провайдера", async () => {
    server.use(authProvidersHandlers.nonRu());

    renderLoginAt();

    expect(
      await screen.findByRole("button", { name: YANDEX_BUTTON }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: GOOGLE_BUTTON }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: GITHUB_BUTTON }),
    ).toBeInTheDocument();
    expect(screen.getByText(SEPARATOR)).toBeInTheDocument();
  });

  it("держит порядок Яндекс → Google → GitHub, даже если сервер прислал другой", async () => {
    server.use(
      http.get("/api/auth/providers", () =>
        HttpResponse.json({
          providers: ["github", "google", "yandex"],
          password: true,
        }),
      ),
    );

    renderLoginAt();

    await screen.findByRole("button", { name: YANDEX_BUTTON });
    const labels = screen
      .getAllByRole("button")
      .map((button) => button.textContent)
      .filter((label) =>
        [YANDEX_BUTTON, GOOGLE_BUTTON, GITHUB_BUTTON].includes(label ?? ""),
      );
    expect(labels).toEqual([YANDEX_BUTTON, GOOGLE_BUTTON, GITHUB_BUTTON]);
  });

  it("в РФ-гео показывает только кнопку Яндекса", async () => {
    server.use(authProvidersHandlers.ru());

    renderLoginAt();

    expect(
      await screen.findByRole("button", { name: YANDEX_BUTTON }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: GOOGLE_BUTTON }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: GITHUB_BUTTON }),
    ).not.toBeInTheDocument();
  });

  it("молча не рендерит незнакомый id из ответа сервера (позитивный предикат)", async () => {
    server.use(
      http.get("/api/auth/providers", () =>
        HttpResponse.json({
          providers: ["telegram", "yandex"],
          password: true,
        }),
      ),
    );

    renderLoginAt();

    expect(
      await screen.findByRole("button", { name: YANDEX_BUTTON }),
    ).toBeInTheDocument();
    // Незнакомый id не превращается ни в кнопку с подписью, ни в кнопку с
    // сырым идентификатором — он просто отсутствует на экране.
    const buttonLabels = screen
      .getAllByRole("button")
      .map((button) => button.textContent ?? "");
    expect(buttonLabels).not.toContain("telegram");
    expect(
      buttonLabels.filter((label) => /^Войти (с|через) /.test(label)),
    ).toHaveLength(1);
  });

  it("выкладывает блоки в порядке мокапа: форма → разделитель → провайдеры → смена режима", async () => {
    server.use(authProvidersHandlers.ru());

    renderLoginAt();

    const provider = await screen.findByRole("button", {
      name: YANDEX_BUTTON,
    });
    const submit = screen.getByRole("button", { name: "Войти" });
    const separator = screen.getByText(SEPARATOR);
    const switchMode = screen.getByRole("button", {
      name: "Нет аккаунта? Зарегистрироваться",
    });

    const follows = (a: Element, b: Element) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(submit, separator)).toBe(true);
    expect(follows(separator, provider)).toBe(true);
    expect(follows(provider, switchMode)).toBe(true);
  });

  it("на пустом списке провайдеров не рисует ни кнопок, ни разделителя", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("/api/auth/providers", () =>
        HttpResponse.json({ providers: [], password: true }),
      ),
      http.post(LOGIN_URL, tokenResponse),
    );

    renderLoginAt();
    await fillCredentials(user);

    expect(screen.queryByText(SEPARATOR)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: YANDEX_BUTTON }),
    ).not.toBeInTheDocument();
    // Парольный вход не деградирует вместе с блоком провайдеров.
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
  });

  it("на отказе запроса провайдеров оставляет рабочий парольный вход", async () => {
    const user = userEvent.setup();
    server.use(
      authProvidersHandlers.failure(),
      http.post(LOGIN_URL, tokenResponse),
    );

    renderLoginAt();
    await fillCredentials(user);

    expect(screen.queryByText(SEPARATOR)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: YANDEX_BUTTON }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
  });

  it("пока список провайдеров в полёте, форма доступна и разделитель не висит", async () => {
    server.use(
      http.get("/api/auth/providers", async () => {
        await delay(50);
        return HttpResponse.json({ providers: ["yandex"], password: true });
      }),
    );

    renderLoginAt();

    expect(screen.getByLabelText(NAME_FIELD)).toBeEnabled();
    expect(screen.queryByText(SEPARATOR)).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: YANDEX_BUTTON }),
    ).toBeInTheDocument();
    expect(screen.getByText(SEPARATOR)).toBeInTheDocument();
  });

  it("уводит браузер на /authorize с запомненным путём в next, без XHR", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const authorizeCalls = vi.fn();
    server.use(
      authProvidersHandlers.ru(),
      // Кнопка обязана уводить страницу целиком: если вместо навигации уйдёт
      // fetch/XHR, этот хендлер зафиксирует вызов и кейс покраснеет.
      http.get("/api/auth/oauth/:provider/authorize", () => {
        authorizeCalls();
        return HttpResponse.json({});
      }),
    );

    renderLoginAt({
      pathname: "/login",
      state: { from: "/projects/p1?tab=chats" },
    });
    await user.click(
      await screen.findByRole("button", { name: YANDEX_BUTTON }),
    );

    expect(assign).toHaveBeenCalledWith(
      "/api/auth/oauth/yandex/authorize?next=%2Fprojects%2Fp1%3Ftab%3Dchats",
    );
    expect(authorizeCalls).not.toHaveBeenCalled();
  });

  it("при прямом заходе на /login отправляет в next корневой путь", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    server.use(authProvidersHandlers.nonRu());

    renderLoginAt();
    await user.click(
      await screen.findByRole("button", { name: GITHUB_BUTTON }),
    );

    expect(assign).toHaveBeenCalledWith(
      "/api/auth/oauth/github/authorize?next=%2F",
    );
  });
});

// Закрытый реестр кодов возврата из OAuth-флоу (design-brief § Эндпоинты):
// тексты сверяются с таблицей брифа дословно — это контракт стыка backend ↔
// frontend, а не формулировка на усмотрение страницы.
const ERROR_CODES: ReadonlyArray<[string, string]> = [
  [
    "access_denied",
    "Вход отменён. Можно попробовать ещё раз или войти с паролем",
  ],
  ["flow_expired", "Сессия входа истекла — попробуйте ещё раз"],
  [
    "provider_not_available_in_region",
    "Этот способ входа недоступен в вашем регионе",
  ],
  [
    "provider_unavailable",
    "Сервис входа временно недоступен — попробуйте позже",
  ],
  ["oauth_failed", "Не удалось войти — попробуйте ещё раз"],
];

describe("LoginPage — коды ?error= из OAuth-флоу", () => {
  it.each(ERROR_CODES)(
    "на ?error=%s показывает текст из реестра",
    async (code, message) => {
      server.use(authProvidersHandlers.ru());

      renderLoginAt({ pathname: "/login", search: `?error=${code}` });

      expect(await screen.findByText(message)).toBeInTheDocument();
    },
  );

  it("на неизвестном коде показывает generic-текст вместо белого экрана", async () => {
    server.use(authProvidersHandlers.ru());

    renderLoginAt({ pathname: "/login", search: "?error=meteorite" });

    expect(
      await screen.findByText("Не удалось войти — попробуйте ещё раз"),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Вход" })).toBeInTheDocument();
  });

  it("без параметра error не показывает сообщения об ошибке", async () => {
    server.use(authProvidersHandlers.ru());

    renderLoginAt();

    for (const [, message] of ERROR_CODES) {
      expect(screen.queryByText(message)).not.toBeInTheDocument();
    }
  });

  it("гасит сообщение при переключении вход ↔ регистрация", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru());

    renderLoginAt({ pathname: "/login", search: "?error=flow_expired" });
    const message = "Сессия входа истекла — попробуйте ещё раз";
    await screen.findByText(message);

    await user.click(
      screen.getByRole("button", { name: "Нет аккаунта? Зарегистрироваться" }),
    );

    // Отказ прошлого OAuth-флоу не относится к новой форме — он не должен
    // висеть над регистрацией.
    expect(screen.queryByText(message)).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Регистрация" }),
    ).toBeInTheDocument();
  });

  it("не мешает парольному входу: после успешной отправки сообщение уходит вместе со страницей", async () => {
    const user = userEvent.setup();
    server.use(authProvidersHandlers.ru(), http.post(LOGIN_URL, tokenResponse));

    renderLoginAt({ pathname: "/login", search: "?error=flow_expired" });
    await screen.findByText("Сессия входа истекла — попробуйте ещё раз");
    await fillCredentials(user);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByText(HOME_MARKER)).toBeInTheDocument();
  });
});
