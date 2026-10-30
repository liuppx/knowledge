import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderElement } from "../../test/render";
import { PassportLoginPage } from "./PassportLoginPage";

vi.mock("@yeying-community/web3-bs", () => ({
  getProvider: vi.fn(async () => null),
  loginWithWalletIdentity: vi.fn(),
}));

describe("PassportLoginPage", () => {
  it("presents the knowledge context and switches login methods explicitly", async () => {
    const user = userEvent.setup();
    renderElement(<PassportLoginPage onAuthenticated={vi.fn()} />);

    expect(screen.getByRole("heading", { level: 1, name: "让每条知识，都能回到它的证据。" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "进入 Knowledge" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "钱包身份" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("使用钱包签发的身份凭证完成登录。")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "夜莺通行证" }));

    expect(screen.getByRole("button", { name: "夜莺通行证" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "打开夜莺通行证" })).toBeInTheDocument();
    expect(screen.getByText("通过夜莺通行证完成 Passkey 或钱包验证。")).toBeInTheDocument();
  });

  it("announces a missing wallet as a recoverable error", async () => {
    const user = userEvent.setup();
    renderElement(<PassportLoginPage onAuthenticated={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "连接钱包并继续" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("未检测到可用钱包");
  });
});
