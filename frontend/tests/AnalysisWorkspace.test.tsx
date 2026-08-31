import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";
import { reportPdfUrl } from "@/lib/api";

describe("AnalysisWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("shows the legal boundary and upload contract", () => {
    render(<AnalysisWorkspace />);
    expect(screen.getByText("법률 판단이 아닌 검토 보조")).toBeInTheDocument();
    expect(screen.getByLabelText("계약서 파일")).toHaveAttribute("accept", ".txt,.pdf,.docx");
    expect(screen.getByRole("button", { name: "분석 시작" })).toBeDisabled();
  });

  it("does not invent a bank comparison when no verified dataset exists", () => {
    render(<AnalysisWorkspace />);
    expect(screen.getAllByText("은행 비교").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/순위나 추천은 표시하지 않습니다/).length).toBeGreaterThan(0);
  });

  it("builds a safe PDF report download URL", () => {
    expect(reportPdfUrl("analysis/id")).toBe(
      "http://127.0.0.1:8000/api/v1/analyses/analysis%2Fid/report.pdf",
    );
  });

  it("uploads a PDF and exposes the completed report download", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "document-1" }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "analysis-1",
          document_id: "document-1",
          status: "completed",
          disposition: "no_signal",
          experiment_arm: "D",
          result: {
            findings: [
              {
                finding_id: "finding-1",
                source: { masked_text: "은행은 일방적으로 변경한다.", match_span: [4, 9] },
                rule_signal: {
                  rule_id: "rule-1",
                  category: "일방 변경",
                  matched_excerpt: "일방적으로",
                  signal_strength: "medium",
                  rationale: "검토 필요",
                },
                evidence: [],
                verification: { status: "passed" },
                clause: { number: 1, char_start: 0, char_end: 15 },
              },
            ],
            warnings: [],
            clause_count: 1,
            document: {
              masked_text: "은행은 일방적으로 변경한다.",
              pii_types: [],
              pii_replacement_count: 0,
            },
          },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisWorkspace />);

    const file = new File(["%PDF-1.4 synthetic"], "terms.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(screen.getByLabelText("계약서 파일"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));

    const report = await screen.findByRole("link", { name: "PDF 리포트" });
    expect(report).toHaveAttribute(
      "href",
      "http://127.0.0.1:8000/api/v1/analyses/analysis-1/report.pdf",
    );
    expect(report).toHaveAttribute("download");
    expect(screen.getByRole("heading", { name: "마스킹된 전체 문서" })).toBeInTheDocument();
    expect(screen.getByText("일방적으로", { selector: "mark" })).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});
