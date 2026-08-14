import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/test-utils";

import { ProjectActions } from "./ProjectActions";

// Integration (feat-013, блок 2 «Заодно»): меню проекта в сайдбаре и два его
// диалога. Механика переименования и удаления не менялась — менялся язык: до
// правки русский продукт показывал здесь Rename / Delete / «Enter a new name»
// и звал проект английскими кавычками-сущностями. Суита сторожит именно то,
// что человек читает перед необратимым действием, и что диалог удаления
// честно называет, что уедет вместе с проектом (каскад по модели: чаты,
// артефакты, сфера). Сеть здесь не нужна — ни один кейс не доводит мутацию до
// запроса.

const PROJECT_ID = "p1";
const PROJECT_NAME = "Матан";

function renderActions() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}`]}>
      <ProjectActions projectId={PROJECT_ID} projectName={PROJECT_NAME} />
    </MemoryRouter>,
  );
}

/** Триггер меню — единственная кнопка компонента, иконка без подписи. */
async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button"));
}

describe("ProjectActions", () => {
  it("offers rename and delete in Russian", async () => {
    const user = userEvent.setup();
    renderActions();

    await openMenu(user);

    expect(
      await screen.findByRole("menuitem", { name: "Переименовать" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Удалить" }),
    ).toBeInTheDocument();
  });

  it("asks for the new name in Russian, prefilled with the current one", async () => {
    const user = userEvent.setup();
    renderActions();

    await openMenu(user);
    await user.click(
      await screen.findByRole("menuitem", { name: "Переименовать" }),
    );

    expect(await screen.findByText("Переименовать проект")).toBeInTheDocument();
    expect(
      screen.getByText("Введите новое название проекта."),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue(PROJECT_NAME);
    expect(screen.getByRole("button", { name: "Отмена" })).toBeInTheDocument();
    // Значение не изменилось — сохранять нечего.
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("names the project and what goes with it before deleting", async () => {
    const user = userEvent.setup();
    renderActions();

    await openMenu(user);
    await user.click(await screen.findByRole("menuitem", { name: "Удалить" }));

    expect(await screen.findByText("Удалить проект")).toBeInTheDocument();
    expect(screen.getByText(/Удалить «Матан»\?/)).toBeInTheDocument();
    expect(
      screen.getByText(/Все чаты, артефакты и сфера знаний проекта будут/),
    ).toBeInTheDocument();
    expect(screen.getByText(/нельзя отменить/)).toBeInTheDocument();
  });
});
