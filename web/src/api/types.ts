import type { components, paths } from "./schema";

/** Shorthand for a generated response/request schema: `Schema<"KBResponse">`. */
export type Schema<Name extends keyof components["schemas"]> = components["schemas"][Name];

export type ApiPaths = paths;
