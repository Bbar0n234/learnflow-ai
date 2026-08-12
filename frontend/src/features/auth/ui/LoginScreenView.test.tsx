import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  LoginScreenView,
  type AuthMode,
  type AuthProvider,
  type LoginScreenViewProps,
} from "@/features/auth";
import { PROVIDER_LABELS } from "@/test/provider-labels";

// Integration (экран целиком под RTL, без сети и провайдеров: компонент чисто
// презентационный и в квери не ходит). Суита фиксирует **контракт стыка с
// feat-008**: у экрана сегодня нет потребителя — `pages/login` собирает
// параллельная итерация, — и единственная страховка от того, что она подключит
// логику к экрану, который ведёт себя иначе, чем описано в summary трека, это
// проверка каждого пропа по его документированной семантике.
//
// Импорт идёт через публичный API слайса (`@/features/auth`), а не через файл
// компонента: feat-008 увидит ровно то, что отдаёт `index.ts`, и суита краснеет,
// если из барреля пропадёт компонент или тип контракта.
//
// Вид экрана (цвета знаков провайдеров, отступы, радиусы, тень карточки,
// брейкпоинт `lg`) здесь не проверяется — jsdom не исполняет CSS. Живая сверка
// с мокапом по числам сделана треком (summary T6.4); регресс вида — ручные
// кейсы {T6.1}–{T6.8}.

// Утверждённая гео-модель (design-brief, блок 8): РФ — только Яндекс ID
// (149-ФЗ), вне РФ — Яндекс ID, Google, GitHub. VK ID снят полностью.
const RU_PROVIDERS: readonly AuthProvider[] = ["yandex"];
const NON_RU_PROVIDERS: readonly AuthProvider[] = [
  "yandex",
  "google",
  "github",
];

function renderScreen(overrides: Partial<LoginScreenViewProps> = {}) {
  const props: LoginScreenViewProps = {
    mode: "login",
    onModeChange: vi.fn(),
    values: { name: "", password: "", confirmPassword: "" },
    onFieldChange: vi.fn(),
    onSubmit: vi.fn(),
    providers: [],
    onProviderSelect: vi.fn(),
    ...overrides,
  };

  return {
    props,
    user: userEvent.setup(),
    ...render(<LoginScreenView {...props} />),
  };
}

// Подписи собственных кнопок формы — режимными таблицами, по одной на роль,
// зеркально прод-контракту. Плоского списка здесь больше нет: он нёс свою копию
// каждой подписи, и прод-правка подписи сабмита («…» → глагольные формы)
// покрасила разом и его, и кейсы состава провайдеров, которые на него опираются.
// Тип `Record<AuthMode, string>` сторожит состав режимов через `tsc`.
const SUBMIT_LABELS: Record<AuthMode, string> = {
  login: "Войти",
  register: "Создать аккаунт",
};

// На время отправки подпись остаётся именем: «…» именем не было — кнопка
// пропадала из поиска по доступному имени и озвучивалась как «кнопка,
// многоточие». Состояние объявляется отдельно, атрибутом `aria-busy`, а не
// съеденной подписью.
const SUBMITTING_LABELS: Record<AuthMode, string> = {
  login: "Входим…",
  register: "Создаём аккаунт…",
};

const SWITCH_LABELS: Record<AuthMode, string> = {
  login: "Нет аккаунта? Зарегистрироваться",
  register: "Уже есть аккаунт? Войти",
};

// Собственные кнопки формы — всё, что не относится к блоку провайдеров: сабмит
// в четырёх его подписях (обе режимные + обе на время отправки) и переключатель
// режима. Всё остальное на экране — кнопка провайдера.
const OWN_FORM_BUTTON_NAMES: readonly string[] = [
  ...Object.values(SUBMIT_LABELS),
  ...Object.values(SUBMITTING_LABELS),
  ...Object.values(SWITCH_LABELS),
];

/**
 * Подписи всех кнопок провайдеров на экране, в порядке DOM — так проверяется и
 * состав, и порядок разом. Скрытые от скринридера узлы (знак Яндекса — inline-SVG
 * с текстовой «Я») из подписи убираются: в доступное имя кнопки они не входят.
 *
 * Отбор идёт **исключением собственных кнопок формы**, а не белым списком
 * известных подписей: иначе лишняя кнопка провайдера с незнакомой подписью
 * (например, вернувшийся VK ID) молча отфильтровалась бы, и «состав» читался бы
 * как «эти в таком порядке среди известных» вместо «ровно эти».
 */
function providerButtonNames(): string[] {
  return screen
    .getAllByRole("button")
    .map((button) => {
      const visible = button.cloneNode(true) as HTMLElement;
      visible
        .querySelectorAll('[aria-hidden="true"]')
        .forEach((hidden) => hidden.remove());
      return visible.textContent?.trim() ?? "";
    })
    .filter((name) => !OWN_FORM_BUTTON_NAMES.includes(name));
}

describe("LoginScreenView — режимы входа и регистрации", () => {
  it("в режиме входа показывает два поля и подпись «Войти»", () => {
    renderScreen({ mode: "login" });

    expect(screen.getByText("Вход")).toBeInTheDocument();
    expect(
      screen.getByText("Продолжите работу со своими проектами."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Имя пользователя")).toBeInTheDocument();
    expect(screen.getByLabelText("Пароль")).toBeInTheDocument();
    expect(screen.queryByLabelText("Повторите пароль")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: SUBMIT_LABELS.login }),
    ).toBeInTheDocument();
  });

  it("в режиме регистрации добавляет подтверждение пароля и подпись «Создать аккаунт»", () => {
    renderScreen({ mode: "register" });

    expect(screen.getByText("Регистрация")).toBeInTheDocument();
    expect(
      screen.getByText("Придумайте имя и пароль — этого достаточно."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Повторите пароль")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: SUBMIT_LABELS.register }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: SUBMIT_LABELS.login }),
    ).not.toBeInTheDocument();
  });

  const switches: [AuthMode, string, AuthMode][] = [
    ["login", SWITCH_LABELS.login, "register"],
    ["register", SWITCH_LABELS.register, "login"],
  ];

  it.each(switches)(
    "из режима %s переключатель «%s» зовёт onModeChange(%s)",
    async (mode, label, expected) => {
      const { props, user } = renderScreen({ mode });

      await user.click(screen.getByRole("button", { name: label }));

      expect(props.onModeChange).toHaveBeenCalledTimes(1);
      expect(props.onModeChange).toHaveBeenCalledWith(expected);
    },
  );

  // Переключатель стоит внутри `<form>`: дефолтный `type="submit"` отправил бы
  // форму вместо смены режима — потребитель получил бы запрос логина на клик
  // «Нет аккаунта?».
  it("переключение режима не отправляет форму", async () => {
    const { props, user } = renderScreen({ mode: "login" });

    await user.click(screen.getByRole("button", { name: SWITCH_LABELS.login }));

    expect(props.onSubmit).not.toHaveBeenCalled();
  });
});

describe("LoginScreenView — поля формы", () => {
  it("в режиме входа подсказывает менеджеру паролей существующий пароль", () => {
    renderScreen({ mode: "login" });

    expect(screen.getByLabelText("Имя пользователя")).toHaveAttribute(
      "autocomplete",
      "username",
    );
    expect(screen.getByLabelText("Пароль")).toHaveAttribute(
      "autocomplete",
      "current-password",
    );
  });

  // Отступление от буквы мокапа (plan-review п.2): статичный мокап всегда несёт
  // `current-password`, и буквальный перенос заставил бы менеджер паролей
  // подставлять существующий пароль вместо генерации нового.
  it("в режиме регистрации просит менеджер паролей сгенерировать новый", () => {
    renderScreen({ mode: "register" });

    expect(screen.getByLabelText("Пароль")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
    expect(screen.getByLabelText("Повторите пароль")).toHaveAttribute(
      "autocomplete",
      "new-password",
    );
  });

  it("сообщает потребителю ввод в поле имени", async () => {
    const { props, user } = renderScreen();

    await user.type(screen.getByLabelText("Имя пользователя"), "a");

    expect(props.onFieldChange).toHaveBeenCalledWith("name", "a");
  });

  it("сообщает потребителю ввод в поле пароля", async () => {
    const { props, user } = renderScreen();

    await user.type(screen.getByLabelText("Пароль"), "s");

    expect(props.onFieldChange).toHaveBeenCalledWith("password", "s");
  });

  it("сообщает потребителю ввод в поле подтверждения пароля", async () => {
    const { props, user } = renderScreen({ mode: "register" });

    await user.type(screen.getByLabelText("Повторите пароль"), "s");

    expect(props.onFieldChange).toHaveBeenCalledWith("confirmPassword", "s");
  });

  it("показывает значения из props, а не собственное состояние", () => {
    renderScreen({
      mode: "register",
      values: { name: "electric", password: "pw", confirmPassword: "pw2" },
    });

    expect(screen.getByLabelText("Имя пользователя")).toHaveValue("electric");
    expect(screen.getByLabelText("Пароль")).toHaveValue("pw");
    expect(screen.getByLabelText("Повторите пароль")).toHaveValue("pw2");
  });

  it("ставит фокус в поле имени при открытии экрана", () => {
    renderScreen();

    expect(screen.getByLabelText("Имя пользователя")).toHaveFocus();
  });
});

describe("LoginScreenView — отправка формы", () => {
  // Валидация целиком за потребителем (design-brief блок 8, «Уточнение
  // архитектора»): пустые поля не блокируют кнопку, иначе экран молча не
  // отвечает на клик вместо того, чтобы объяснить.
  it("зовёт onSubmit даже с пустыми полями и ничего не валидирует сам", async () => {
    const { props, user } = renderScreen({
      values: { name: "", password: "", confirmPassword: "" },
    });

    const submit = screen.getByRole("button", { name: SUBMIT_LABELS.login });
    expect(submit).toBeEnabled();

    await user.click(submit);

    expect(props.onSubmit).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/Введите имя и пароль/)).not.toBeInTheDocument();
  });

  it("отправляет форму по Enter в поле", async () => {
    const { props, user } = renderScreen();

    await user.type(screen.getByLabelText("Имя пользователя"), "{Enter}");

    expect(props.onSubmit).toHaveBeenCalledTimes(1);
  });

  it("во время отправки блокирует поля, сабмит и провайдеров", async () => {
    const { props, user } = renderScreen({
      submitting: true,
      providers: NON_RU_PROVIDERS,
    });

    expect(screen.getByLabelText("Имя пользователя")).toBeDisabled();
    expect(screen.getByLabelText("Пароль")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: PROVIDER_LABELS.yandex }),
    ).toBeDisabled();

    const submit = screen.getByRole("button", {
      name: SUBMITTING_LABELS.login,
    });
    expect(submit).toBeDisabled();

    await user.click(submit);
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  // Отправка — состояние кнопки, а не пропажа её имени. Раньше подпись
  // схлопывалась в «…»: доступное имя вырождалось, кнопку нельзя было найти по
  // имени, а скринридер читал «кнопка, многоточие». Кейс требует обе половины
  // разом — осмысленную режимную подпись и объявленный `aria-busy`, — и
  // отдельно проверяет обратный переход: вне отправки состояние не объявляется,
  // иначе «занята всегда» читается так же, как «занята сейчас».
  const submittingModes = Object.keys(SUBMITTING_LABELS) as AuthMode[];

  it.each(submittingModes)(
    "в режиме %s подписывает отправку глаголом и объявляет её через aria-busy",
    (mode) => {
      const { props, rerender } = renderScreen({ mode });

      expect(
        screen.getByRole("button", { name: SUBMIT_LABELS[mode] }),
      ).not.toHaveAttribute("aria-busy");

      rerender(<LoginScreenView {...props} submitting />);

      const submit = screen.getByRole("button", {
        name: SUBMITTING_LABELS[mode],
      });
      expect(submit).toHaveAttribute("aria-busy", "true");
      expect(
        screen.queryByRole("button", { name: "…" }),
      ).not.toBeInTheDocument();
    },
  );
});

describe("LoginScreenView — ошибка", () => {
  it("показывает переданный текст ошибки карточкой", () => {
    renderScreen({ error: "Пароли не совпадают." });

    expect(screen.getByText("Пароли не совпадают.")).toBeInTheDocument();
  });

  const emptyErrors: [string, string | null | undefined][] = [
    ["undefined", undefined],
    ["null", null],
    ["пустая строка", ""],
  ];

  // Отсутствие карточки проверяется **переходом**, а не первым рендером: у
  // `ErrorCard` нет ни роли, ни `data-slot`, поэтому «карточки нет» в чистом
  // рендере ничем не отличается от «карточка есть, но текста в ней нет». Узел
  // берётся до снятия ошибки: если экран начнёт рисовать карточку всегда, React
  // переиспользует тот же узел (тип и позиция не изменились) — он останется в
  // документе, пустой, и кейс покраснеет.
  it.each(emptyErrors)(
    "убирает карточку ошибки, когда error становится %s",
    (_name, error) => {
      const { props, rerender } = renderScreen({
        error: "Пароли не совпадают.",
        values: { name: "a", password: "", confirmPassword: "" },
      });

      const card = screen.getByText("Пароли не совпадают.").parentElement;
      expect(card).toBeInTheDocument();

      rerender(<LoginScreenView {...props} error={error} />);

      expect(card).not.toBeInTheDocument();
      expect(screen.queryByText(/Пароли не совпадают/)).not.toBeInTheDocument();
    },
  );
});

describe("LoginScreenView — гео-состав провайдеров", () => {
  // РФ: единственный разрешённый провайдер — Яндекс ID (149-ФЗ).
  it("для РФ показывает только Яндекс ID", () => {
    renderScreen({ providers: RU_PROVIDERS });

    expect(providerButtonNames()).toEqual([PROVIDER_LABELS.yandex]);
    expect(screen.getByText("или")).toBeInTheDocument();
  });

  it("вне РФ показывает Яндекс ID, Google и GitHub в порядке состава", () => {
    renderScreen({ providers: NON_RU_PROVIDERS });

    expect(providerButtonNames()).toEqual([
      PROVIDER_LABELS.yandex,
      PROVIDER_LABELS.google,
      PROVIDER_LABELS.github,
    ]);
  });

  // VK ID снят решением архитектора полностью (регистрация приложения требует
  // подтверждённое бизнес-лицо, которого у проекта нет). Его молчаливое
  // возвращение — ровно то, что этот кейс обязан ловить: ни в одном гео-составе
  // экран не упоминает VK ни кнопкой, ни текстом.
  const compositions: [string, readonly AuthProvider[] | undefined][] = [
    ["РФ", RU_PROVIDERS],
    ["вне РФ", NON_RU_PROVIDERS],
    ["пустой состав", []],
    ["состав ещё грузится", undefined],
  ];

  it.each(compositions)("не предлагает VK ID (%s)", (_name, providers) => {
    renderScreen({ providers });

    expect(screen.queryByText(/vk|вконтакте/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /vk|вконтакте/i }),
    ).not.toBeInTheDocument();
  });

  it("зовёт onProviderSelect с выбранным провайдером", async () => {
    const { props, user } = renderScreen({ providers: NON_RU_PROVIDERS });

    await user.click(
      screen.getByRole("button", { name: PROVIDER_LABELS.google }),
    );

    expect(props.onProviderSelect).toHaveBeenCalledTimes(1);
    expect(props.onProviderSelect).toHaveBeenCalledWith("google");
    // Кнопка провайдера стоит внутри формы — она не должна её отправлять.
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  // Три состояния `providers` — тот самый шов, ради которого выбрана форма
  // трека (plan-review п.1): состав приходит из запроса, на первом рендере он
  // неизвестен, и карточка не должна прыгать, когда состав приедет.
  it("при загрузке гео рисует разделитель и плашку-резерв вместо кнопок", () => {
    const { container } = renderScreen({ providers: undefined });

    expect(screen.getByText("или")).toBeInTheDocument();
    expect(providerButtonNames()).toEqual([]);
    // Плашка-резерв наблюдаема только разметкой: её роль — занять высоту
    // будущей кнопки, а высоты в jsdom нет.
    expect(
      container.querySelector('[data-slot="skeleton"]'),
    ).toBeInTheDocument();
  });

  it("при пустом составе не рисует ни разделитель, ни блок провайдеров", () => {
    const { container } = renderScreen({ providers: [] });

    expect(screen.queryByText("или")).not.toBeInTheDocument();
    expect(providerButtonNames()).toEqual([]);
    expect(container.querySelector('[data-slot="skeleton"]')).toBeNull();
  });
});

describe("LoginScreenView — брендовая половина экрана", () => {
  // Экран — не одна карточка формы: брендовость и есть предмет трека, а
  // `AuthLayout` можно молча вынести из компонента (или заменить форком с теми
  // же подписями формы), и все остальные кейсы останутся зелёными — они смотрят
  // только внутрь `<form>`. Сцена и тэглайн — DOM-факты, которые jsdom
  // исполняет; геометрия и брейкпоинт — ручные {T6.1}, {T6.6}.
  it("собран из брендовой рамки: сцена auth-hero и тэглайн на месте", () => {
    renderScreen();

    expect(
      screen.getByRole("img", { name: "Иллюстрация: Электрик приветствует" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Учитесь со своим ИИ-наставником/),
    ).toBeInTheDocument();
  });
});

describe("LoginScreenView — клавиатура и раскладка", () => {
  // Порядок обхода задан порядком узлов (явных `tabIndex` в экране нет):
  // имя → пароль → сабмит → провайдеры → переключатель режима.
  it("обходит форму табом в порядке чтения", async () => {
    const { user } = renderScreen({ providers: RU_PROVIDERS });

    const order = [
      screen.getByLabelText("Имя пользователя"),
      screen.getByLabelText("Пароль"),
      screen.getByRole("button", { name: SUBMIT_LABELS.login }),
      screen.getByRole("button", { name: PROVIDER_LABELS.yandex }),
      screen.getByRole("button", { name: SWITCH_LABELS.login }),
    ];

    // Отправная точка задаётся явно, а не автофокусом: обход и автофокус —
    // разные обещания экрана, и падать они должны порознь.
    order[0]?.focus();
    for (const element of order.slice(1)) {
      await user.tab();
      expect(element).toHaveFocus();
    }
  });

  // Класс — сам наблюдаемый контракт: `className` существует затем, чтобы
  // `pages/login` из feat-008 посадил экран в свою геометрию, не форкая его.
  it("пробрасывает className в корень экрана", () => {
    const { container } = renderScreen({ className: "mt-6" });

    expect(container.firstElementChild).toHaveClass("mt-6");
  });
});
