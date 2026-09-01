import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";

const detailedFinding = {
  finding_id: "finding-1",
  source: { masked_text: "은행은 일방적으로 변경한다.", match_span: [4, 9] as [number, number] },
  rule_signal: {
    rule_id: "R04_UNILATERAL_CHANGE",
    rule_version: "0.2.0",
    rule_name: "사업자의 일방적 계약내용 변경",
    category: "unilateral_change",
    matched_excerpt: "일방적으로",
    signal_strength: "medium",
    rationale: "검토 필요",
  },
  explanation: {
    why_flagged: "고객의 선택 절차 없이 일방적으로 변경할 수 있는 구조입니다.",
    possible_impact: "예상하지 못한 비용을 부담할 수 있습니다.",
    review_points: ["변경 전 충분한 통지 기간이 있는지"],
    suggested_revision: "최소 30일 전에 변경 사유를 통지합니다.",
    disclaimer: "검토용 예시이며 법률 자문이나 확정 수정안이 아닙니다.",
  },
  evidence: [{
    evidence_id: "law-1",
    title: "약관의 규제에 관한 법률 제10조",
    status: "verified",
    authority: "국가법령정보센터",
    source_url: "https://example.invalid/law",
    quoted_excerpt: "사업자는 상당한 이유 없이 급부의 내용을 일방적으로 결정할 수 없다.",
    relevance_score: 0.91,
    manifest_version: "public-v0.1",
  }],
  grounding: { status: "grounded", retrieved_count: 1, corpus_version: "public-v0.1" },
  assessment: {
    risk_level: "medium",
    summary: "AI 보충 요약",
    rationale: "계약 전체 문맥 확인 필요",
    counter_considerations: ["법령상 허용 사유"],
    review_questions: ["고객의 거절권이 있습니까?"],
  },
  verification: { status: "failed", issues: [{ code: "VERIFY_TEST", message: "검증 예시" }] },
  clause: { number: 1, char_start: 0, char_end: 15 },
};

function mockUploadResult(overrides: Record<string, unknown> = {}) {
  return vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "document-1" }) })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "analysis-1",
        document_id: "document-1",
        status: "completed",
        disposition: "ready_for_review",
        experiment_arm: "D",
        result: {
          findings: [detailedFinding],
          warnings: [],
          clause_count: 1,
          document: { masked_text: "은행은 일방적으로 변경한다.", pii_types: [], pii_replacement_count: 0 },
        },
        ...overrides,
      }),
    });
}

async function upload(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  render(<AnalysisWorkspace />);
  fireEvent.change(screen.getByLabelText("계약서 파일"), {
    target: { files: [new File(["synthetic"], "terms.txt", { type: "text/plain" })] },
  });
  fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
  await screen.findByRole("button", { name: "PDF 리포트" });
}

describe("AnalysisWorkspace", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

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

  it("renders the exact match, explanation, revision, evidence, and verification detail", async () => {
    const fetchMock = mockUploadResult();
    await upload(fetchMock);

    expect(screen.getByRole("heading", { name: "제1조 · 사업자의 일방적 계약내용 변경" })).toBeInTheDocument();
    expect(screen.getAllByText("일방적으로", { selector: "mark" })).toHaveLength(2);
    expect(screen.getByText("고객의 선택 절차 없이 일방적으로 변경할 수 있는 구조입니다.")).toBeInTheDocument();
    expect(screen.getByText("예상하지 못한 비용을 부담할 수 있습니다.")).toBeInTheDocument();
    expect(screen.getByText("변경 전 충분한 통지 기간이 있는지")).toBeInTheDocument();
    expect(screen.getByText("최소 30일 전에 변경 사유를 통지합니다.")).toBeInTheDocument();
    expect(screen.getByText(/사업자는 상당한 이유 없이/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "법령 원문 열기" })).toHaveAttribute("href", "https://example.invalid/law");
    expect(screen.getByText(/VERIFY_TEST/)).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("explains that no signal is not a safety or legality guarantee", async () => {
    const fetchMock = mockUploadResult({
      disposition: "no_signal",
      result: { findings: [], warnings: [], clause_count: 1 },
    });
    await upload(fetchMock);
    expect(screen.getByText(/현재 8개 실험 규칙에서 위험 신호가 탐지되지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText(/안전성이나 적법성을 보장하지 않습니다/)).toBeInTheDocument();
  });

  it("shows a failed analysis code and preserves the status recheck action", async () => {
    const fetchMock = mockUploadResult({ status: "failed", disposition: "needs_review", error_code: "LLM_UNAVAILABLE" });
    vi.stubGlobal("fetch", fetchMock);
    render(<AnalysisWorkspace />);
    fireEvent.change(screen.getByLabelText("계약서 파일"), { target: { files: [new File(["x"], "terms.txt")] } });
    fireEvent.click(screen.getByRole("button", { name: "분석 시작" }));
    expect(await screen.findByText(/LLM_UNAVAILABLE/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "상태 다시 확인" })).toBeInTheDocument();
  });
});
