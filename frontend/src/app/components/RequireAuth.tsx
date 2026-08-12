import { Navigate, Outlet, useLocation } from "react-router";
import { getAccessToken } from "@/shared/api/client";

/**
 * Guard над защищённой группой маршрутов. Вердикт нереактивный — читает
 * токен синхронно при рендере, как раньше делал `AuthGate`: бутстрап
 * (`app/model/useAuthBootstrap.ts`) гейтит монтирование маршрутов целиком, так
 * что к моменту рендера гварда «есть ли валидный access» уже решено, и ему не
 * нужно ни знать про бутстрап, ни подписываться на новый стор.
 *
 * `from` — строка `pathname + search + hash`, не объект `location`: значение
 * уходит в `navigate(from)` после успешного входа и в query-параметр `next`
 * (T2.4), где объект location дал бы `next=%5Bobject%20Object%5D`.
 */
export function RequireAuth() {
  const location = useLocation();

  if (!getAccessToken()) {
    const from = `${location.pathname}${location.search}${location.hash}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }

  return <Outlet />;
}
