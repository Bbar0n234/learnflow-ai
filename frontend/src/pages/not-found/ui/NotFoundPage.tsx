import { Link } from "react-router";

import { buttonVariants } from "@/shared/ui/button";
import { StateScreen } from "@/shared/ui/StateScreen";

/**
 * Брендовый 404 (feat-013, блок 7 дизайн-брифа). Рендерится catch-all-роутом
 * `path="*"` внутри `AppLayout` — сайдбар остаётся видимым, пользователь не
 * выпадает из приложения. Не редирект.
 *
 * Презентационный компонент: ни хуков данных, ни логирования.
 *
 * CTA — `Link` со стилями `buttonVariants()`, а не `Button render={<Link/>}`:
 * это навигация, поэтому элемент остаётся ссылкой (активируется Enter, попадает
 * в список ссылок скринридера), а вид primary-кнопки даётся классами.
 */
export function NotFoundPage() {
  return (
    <StateScreen
      scene="not-found"
      alt="Иллюстрация: страница не найдена"
      illustrationClassName="max-w-[360px]"
      title="Страница не найдена"
      description="Такой страницы нет или она переехала. Вернитесь на главную и продолжите оттуда."
      action={
        <Link to="/" className={buttonVariants()}>
          На главную
        </Link>
      }
      className="h-full"
    />
  );
}
