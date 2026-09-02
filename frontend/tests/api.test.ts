import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ClientApiError,
  deleteDocument,
  downloadReport,
  getBankComparison,
  getDocument,
  reportPdfUrl,
  uploadAndAnalyze,
  waitForAnalysis,
} from "@/lib/api";

describe("same-origin API client", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("uses relative URLs for upload, analysis creation, polling, and PDF", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "document-1" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "analysis-1", document_id: "document-1", status: "queued", disposition: "pending", experiment_arm: "A" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "analysis-1", document_id: "document-1", status: "completed", disposition: "no_signal", experiment_arm: "A" }) });
    vi.stubGlobal("fetch", fetchMock);
    const created = await uploadAndAnalyze(new File(["x"], "terms.txt"), "A");
    await waitForAnalysis(created, { maxAttempts: 2, pollIntervalMs: 0 });

    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/documents");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/documents/document-1/analyses");
    expect(fetchMock.mock.calls[2][0]).toBe("/api/v1/analyses/analysis-1");
    expect(reportPdfUrl("analysis/id")).toBe("/api/v1/analyses/analysis%2Fid/report.pdf");
  });

  it("uses relative URLs for PDF download and document deletion", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:report"),
      revokeObjectURL: vi.fn(),
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, blob: async () => new Blob(["%PDF-"]) })
      .mockResolvedValueOnce({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await downloadReport("analysis-1");
    await deleteDocument("document-1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/analyses/analysis-1/report.pdf");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/documents/document-1");
    expect(click).toHaveBeenCalledOnce();
  });

  it("maps encrypted PDF errors to stable Korean guidance without raw details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: "PDF_ENCRYPTED: secret parser detail" }),
    }));
    await expect(uploadAndAnalyze(new File(["x"], "locked.pdf"), "D")).rejects.toMatchObject({
      name: "ClientApiError",
      stage: "upload",
      code: "PDF_ENCRYPTED",
      retryable: false,
      message: "암호화된 PDF는 처리할 수 없습니다. 암호를 해제한 사본을 업로드하세요.",
    });
  });

  it("continues polling through analyzing and retrying states", async () => {
    const initial = { id: "a1", document_id: "d1", status: "queued", disposition: "pending", experiment_arm: "D" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...initial, status: "analyzing", progress: { state: "analyzing", percent: 25 } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...initial, status: "queued", progress: { state: "retrying", percent: 0 } }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ ...initial, status: "completed", disposition: "no_signal" }) });
    vi.stubGlobal("fetch", fetchMock);
    const result = await waitForAnalysis(initial, { maxAttempts: 4, pollIntervalMs: 0 });
    expect(result.status).toBe("completed");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("sends bank name and product type as form fields when provided", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "document-1" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "analysis-1", document_id: "document-1", status: "queued", disposition: "pending", experiment_arm: "A" }) });
    vi.stubGlobal("fetch", fetchMock);
    await uploadAndAnalyze(new File(["x"], "terms.txt"), "A", "우리은행", "loan");
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("bank_name")).toBe("우리은행");
    expect(body.get("product_type")).toBe("loan");
  });

  it("uses relative URLs for document metadata and bank comparison lookups", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "document-1", bank_name: "우리은행", product_type: "loan" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ comparison_status: "ready", pros: [], cons: [], neutral: [] }) });
    vi.stubGlobal("fetch", fetchMock);
    await getDocument("document-1");
    await getBankComparison("analysis-1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/documents/document-1");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/analyses/analysis-1/bank-comparison");
  });

  it("maps the not-tagged comparison error to stable Korean guidance", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "COMPARISON_DOCUMENT_NOT_TAGGED: 은행명과 상품유형을 입력한 문서만 타은행과 비교할 수 있습니다." }),
    }));
    await expect(getBankComparison("analysis-1")).rejects.toMatchObject({
      name: "ClientApiError",
      stage: "compare",
      code: "COMPARISON_DOCUMENT_NOT_TAGGED",
      retryable: false,
      message: "은행명과 상품유형을 입력한 문서만 타은행과 비교할 수 있습니다.",
    });
  });

  it("preserves the analysis ID when the polling budget is exhausted", async () => {
    const initial = { id: "keep-this-id", document_id: "d1", status: "queued", disposition: "pending", experiment_arm: "D" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => initial }));
    try {
      await waitForAnalysis(initial, { maxAttempts: 1, pollIntervalMs: 0 });
      throw new Error("expected timeout");
    } catch (reason) {
      expect(reason).toBeInstanceOf(ClientApiError);
      expect(reason).toMatchObject({ code: "ANALYSIS_TIMEOUT", retryable: true });
      expect(initial.id).toBe("keep-this-id");
    }
  });
});
