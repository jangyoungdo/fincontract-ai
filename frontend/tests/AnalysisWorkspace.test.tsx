import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AnalysisWorkspace } from "@/components/AnalysisWorkspace";

const detailedFinding = {
  finding_id: "finding-1",
  summary_sentence: "은행 조건과 관련해 변경 위험 신호가 확인되어 적용 범위를 검토해야 합니다.",
  source: { masked_text: "은행은 일방적으로 변경한다.", match_span: [4, 9] as [number, number], page_number: 3, preview_status: "text_only", preview_ids: [] },
  rule_signal: {
    rule_id: "R04_UNILATERAL_CHANGE",
    rule_version: "0.2.0",
    rule_name: "사업자의 일방적 계약내용 변경",
    category: "unilateral_change",
    matched_excerpt: "일방적으로",
    risk_span: [0, 14] as [number, number],
    matched_elements: [
      { label: "행사 주체", excerpt: "은행", span: [0, 2] as [number, number] },
      { label: "변경 권한", excerpt: "일방적으로", span: [4, 9] as [number, number] },
      { label: "변경 행위", excerpt: "변경한다", span: [10, 14] as [number, number] },
    ],
    signal_strength: "medium",
    rationale: "검토 필요",
  },
  explanation: {
    why_flagged: "고객의 선택 절차 없이 일방적으로 변경할 수 있는 구조입니다.",
    possible_impact: "예상하지 못한 비용을 부담할 수 있습니다.",
    review_points: ["변경 전 충분한 통지 기간이 있는지"],
    suggested_revision: "최소 30일 전에 변경 사유를 통지합니다.",
    revision_points: ["변경 사유를 객관적으로 한정합니다.", "고객에게 거절 선택권을 제공합니다."],
    example_clause: "불리한 변경은 사전에 개별 통지하고 고객에게 거절 선택권을 제공합니다.",
    guidance_version: "revision-guidance-v0.1.0",
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

function mockUploadResult(overrides: Record<string, unknown> = {}, warnings: string[] = []) {
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
          warnings,
          clause_count: 1,
          summary: { headline: "이 문서에서는 계약 변경 관련 규칙 위험 신호 1건이 확인되었습니다.", top_categories: ["사업자의 일방적 계약내용 변경"] },
          document: { pii_types: [], pii_replacement_count: 0, page_count: 3, source_type: "pdf" },
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
    expect(screen.getByRole("heading", { name: "실험 문서로 바로 확인해 보세요" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /실험용 계약서 11종 다운로드/ })).toHaveAttribute("href", "/demo/fincontract-ai-demo-data-v1.zip");
    expect(screen.getByRole("link", { name: /실험용 계약서 11종 다운로드/ })).toHaveAttribute("download");
    expect(screen.getByLabelText("계약서 파일")).toHaveAttribute("accept", ".txt,.pdf,.docx");
    expect(screen.getByRole("button", { name: "분석 시작" })).toBeDisabled();
    expect(screen.queryByText("실험군")).not.toBeInTheDocument();
  });

  it("keeps the first-visit experience focused on the demo workflow", () => {
    render(<AnalysisWorkspace />);
    expect(screen.getByLabelText("실험 서비스 체험 순서")).toBeInTheDocument();
    expect(screen.getByText("압축을 풀고 01번 문서를 선택합니다.")).toBeInTheDocument();
    expect(screen.queryByText("은행 비교")).not.toBeInTheDocument();
  });

  it("renders concise summaries, page context, masked evidence, and collapsed detail", async () => {
    const fetchMock = mockUploadResult();
    await upload(fetchMock);

    expect(screen.queryByRole("heading", { name: "실험 문서로 바로 확인해 보세요" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제1조 · PDF 3페이지 · 사업자의 일방적 계약내용 변경" })).toBeInTheDocument();
    expect(screen.getByText("이 문서에서는 계약 변경 관련 규칙 위험 신호 1건이 확인되었습니다.")).toBeInTheDocument();
    expect(screen.getByText("은행 조건과 관련해 변경 위험 신호가 확인되어 적용 범위를 검토해야 합니다.")).toBeInTheDocument();
    expect(screen.getAllByText("일방적으로", { selector: "mark" })).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "탐지된 위험 구조" })).toBeInTheDocument();
    expect(screen.getByText(/단일 단어가 아니라/)).toBeInTheDocument();
    expect(screen.getByText("행사 주체")).toBeInTheDocument();
    expect(screen.getByText("법적 근거 추가 확인 필요")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "마스킹된 전체 문서" })).not.toBeInTheDocument();
    expect(screen.getByText("고객의 선택 절차 없이 일방적으로 변경할 수 있는 구조입니다.")).toBeInTheDocument();
    expect(screen.getByText("예상하지 못한 비용을 부담할 수 있습니다.")).toBeInTheDocument();
    expect(screen.getByText("변경 전 충분한 통지 기간이 있는지")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "수정 방향" })).toBeInTheDocument();
    expect(screen.getByText("변경 사유를 객관적으로 한정합니다.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "검토용 예시 문안" })).toBeInTheDocument();
    expect(screen.getByText("불리한 변경은 사전에 개별 통지하고 고객에게 거절 선택권을 제공합니다.")).toBeInTheDocument();
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
    expect(screen.getByText(/현재 19개 규칙과 추가 의미 검토에서 위험 신호가 탐지되지 않았습니다/)).toBeInTheDocument();
    expect(screen.getByText(/안전성이나 적법성을 보장하지 않습니다/)).toBeInTheDocument();
  });

  it("hides rejected OpenAI candidates while preserving actionable warnings", async () => {
    const fetchMock = mockUploadResult({}, ["OPENAI_CONTEXT_OUTPUT_REJECTED", "LLM_QUOTA_EXCEEDED"]);
    await upload(fetchMock);

    expect(screen.queryByText(/원문 인용이나 분류 검증/)).not.toBeInTheDocument();
    expect(screen.queryByText("OPENAI_CONTEXT_OUTPUT_REJECTED")).not.toBeInTheDocument();
    expect(screen.getByText(/OpenAI API 사용 한도로 문맥 검토를 생략했습니다/)).toBeInTheDocument();
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
