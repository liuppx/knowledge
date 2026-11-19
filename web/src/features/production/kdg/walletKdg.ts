import { getProvider } from "@yeying-community/web3-bs";

/**
 * 夜莺钱包的知行图(KnowDoGraph)接口:钱包保管知行图账户、自己编码意图、在弹窗里给用户看摘要、确认后签名。
 * 网页与 Knowledge 后端都不接触私钥。接口约定见夜莺钱包 docs/protocols/知行图协议.md。
 */
type Eip1193 = { request: (args: { method: string; params?: unknown[] }) => Promise<unknown> };

async function provider(): Promise<Eip1193> {
  const p = (await getProvider({ preferYeYing: true, timeoutMs: 3000 })) as Eip1193 | null;
  if (!p) throw new Error("未检测到夜莺钱包，请安装并解锁夜莺钱包扩展。");
  return p;
}

/** 钱包报错 → 给用户看的说明。 */
export function kdgWalletError(cause: unknown): Error {
  const e = cause as { code?: number; message?: string } | null;
  const code = e?.code;
  const message = String(e?.message ?? cause ?? "");
  if (code === 4001 || /rejected/i.test(message)) return new Error("你在钱包里取消了。");
  if (code === 4900 || /知行图(密钥|账户)/.test(message)) {
    return new Error("钱包里还没有知行图账户：打开夜莺钱包「账户管理 → 导入钱包」，网络选「知行图」导入后再试。");
  }
  if (code === 4100) return new Error("这个网站还没有连接你的知行图账户，请重新上链并在钱包里确认连接。");
  if (code === -32601 || /not found|not supported/i.test(message)) return new Error("你的夜莺钱包还不支持知行图，请升级到最新版本。");
  return new Error(message || "钱包出错了。");
}

/** 取钱包里知行图账户的公钥(首次会弹窗请用户确认连接)。 */
export async function requestKdgPubkey(): Promise<string> {
  const p = await provider();
  let accounts: unknown;
  try {
    accounts = await p.request({ method: "zhixing_requestAccounts" });
  } catch (cause) {
    throw kdgWalletError(cause);
  }
  const pubkey = String((accounts as string[] | undefined)?.[0] ?? "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(pubkey)) throw new Error("钱包返回的不是知行图公钥。");
  return pubkey;
}

/** 请钱包对意图签名;返回 op ‖ 签名 的十六进制,以及签名所用的公钥。 */
export async function signKdgIntent(intent: { actor: string; nonce: string; action: unknown }): Promise<{ signed: string; address: string }> {
  const p = await provider();
  let out: unknown;
  try {
    out = await p.request({ method: "zhixing_signKnowledgeOp", params: [{ actor: intent.actor, nonce: intent.nonce, action: intent.action }] });
  } catch (cause) {
    throw kdgWalletError(cause);
  }
  const result = out as { signed?: string; address?: string } | null;
  if (!result?.signed || !result.address) throw new Error("钱包没有返回签名。");
  return { signed: result.signed, address: result.address };
}
