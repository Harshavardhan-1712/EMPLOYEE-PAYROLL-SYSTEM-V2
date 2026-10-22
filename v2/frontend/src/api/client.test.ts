import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, AUTH_EXPIRED_EVENT, qs } from "./client";

const reply = (status: number, body?: unknown) => vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
afterEach(() => { document.cookie = "pv2_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT"; });

describe("api client", () => {
  it("parses the structured error envelope", async () => {
    vi.stubGlobal("fetch", reply(422, { error: { code: "validation_error", message: "bad", details: [{ field: "name", message: "required" }] } }));
    const e = await api("/x", { method: "POST", body: {} }).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ status: 422, code: "validation_error", message: "bad", details: [{ field: "name", message: "required" }] });
  });
  it("sends the CSRF header on unsafe methods only, with credentials", async () => {
    document.cookie = "pv2_csrf=tok123";
    const f = reply(200, {}); vi.stubGlobal("fetch", f);
    await api("/a"); await api("/b", { method: "POST", body: { a: 1 } });
    const [, getInit] = f.mock.calls[0] as unknown as [string, RequestInit]; const [, postInit] = f.mock.calls[1] as unknown as [string, RequestInit];
    expect((getInit.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
    expect((postInit.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    expect(postInit.credentials).toBe("include"); expect(postInit.body).toBe('{"a":1}');
  });
  it("maps network failures to a friendly error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    await expect(api("/x")).rejects.toMatchObject({ code: "network_error", status: 0 });
  });
  it("announces expired sessions, but not failed logins", async () => {
    const h = vi.fn(); window.addEventListener(AUTH_EXPIRED_EVENT, h);
    vi.stubGlobal("fetch", reply(401, { error: { code: "unauthenticated", message: "no" } }));
    await api("/employees").catch(() => {}); expect(h).toHaveBeenCalledTimes(1);
    await api("/auth/login", { method: "POST", body: {} }).catch(() => {}); expect(h).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_EXPIRED_EVENT, h);
  });
  it("returns undefined for 204 and falls back on non-JSON errors", async () => {
    vi.stubGlobal("fetch", reply(204)); expect(await api("/x", { method: "DELETE" })).toBeUndefined();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(api("/x")).rejects.toMatchObject({ status: 502, message: "Request failed (502)" });
  });
  it("qs drops empty values", () => expect(qs({ a: "1", b: "", c: undefined, d: 0 })).toBe("?a=1&d=0"));
});
