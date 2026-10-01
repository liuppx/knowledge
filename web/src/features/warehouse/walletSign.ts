import { getProvider, requestAccounts } from "@yeying-community/web3-bs";

/**
 * Ask the user's wallet to personal_sign a server challenge. Mirrors the legacy
 * console: the signing account must be the one logged into Knowledge, otherwise
 * the backend cannot bind the resulting Warehouse credentials to this wallet.
 */
export async function signChallengeWithWallet(message: string, expectedWallet: string): Promise<{ wallet: string; signature: string }> {
  const provider = await getProvider({ preferYeYing: true, timeoutMs: 3000 });
  if (!provider) throw new Error("未检测到可用钱包，请安装并解锁夜莺钱包或兼容钱包扩展。");
  const accounts = (await requestAccounts({ provider })) as string[];
  const wallet = String(accounts?.[0] ?? "").trim();
  if (!wallet) throw new Error("钱包未返回可用账户。");
  if (expectedWallet && wallet.toLowerCase() !== expectedWallet.toLowerCase()) {
    throw new Error(`当前钱包账户 ${wallet} 与 Knowledge 登录地址 ${expectedWallet} 不一致，请先切回相同钱包地址。`);
  }
  const signature = await provider.request({ method: "personal_sign", params: [message, wallet] });
  if (typeof signature !== "string" || !signature) throw new Error("钱包未返回签名。");
  return { wallet, signature };
}
