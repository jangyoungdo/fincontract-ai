import { afterEach, describe, expect, it, vi } from "vitest";
import { ClientApiError, deleteDocument, downloadReport, reportPdfUrl, uploadAndAnalyze, waitForAnalysis } from "@/lib/api";

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
