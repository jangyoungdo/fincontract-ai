"use client";

import { FormEvent, ReactNode, useState } from "react";
import {
  Analysis,
  CandidateFinding,
  ClientApiError,
  Finding,
  deleteDocument,
  downloadReport,
  getAnalysis,
  sourcePreviewUrl,
  uploadAndAnalyze,
  waitForAnalysis,
} from "@/lib/api";

const stageLabels = ["문서 확인", "개인정보 보호", "위험 신호 탐색", "근거·결과 검토"];
const statusLabels: Record<string, string> = {
  queued: "분석 대기",
  analyzing: "분석 중",
  retrying: "자동 재시도 중",
  completed: "분석 완료",
  failed: "분석 실패",
  pending: "준비 중",
};
const dispositionLabels: Record<string, string> = {
  ready_for_review: "검토 준비",
  needs_review: "추가 확인 필요",
  no_signal: "실험 규칙 신호 없음",
  pending: "분석 중",
};
const strengthLabels: Record<string, string> = { low: "낮은 신호", medium: "중간 신호", high: "높은 신호" };
const verificationLabels: Record<string, string> = {
  passed: "법적 근거 확인",
  failed: "법적 근거 추가 확인 필요",
  not_run: "근거 검증 미실행",
};
const warningLabels: Record<string, string> = {
  LLM_BUDGET_SKIPPED: "설명 보강 미실행: 호출 예산에 따라 생략됐으며 규칙 탐지 결과에는 영향이 없습니다.",
  LLM_ENRICHMENT_FAILED: "설명 보강 미실행: 보강 작업을 완료하지 못했으며 규칙 탐지 결과는 그대로 보존되었습니다.",
  SEMANTIC_MODEL_FALLBACK: "고정 E5 모델을 사용할 수 없어 개발용 로컬 fallback이 사용되었습니다.",
  EXPERIMENT_ARM_DEPRECATED: "이전 A/D 요청값은 더 이상 분석 동작을 선택하지 않습니다.",
  OPENAI_CONTEXT_REVIEW_FAILED: "OpenAI 문맥 검토를 완료하지 못했습니다. 규칙 및 로컬 의미 결과는 그대로 보존되었습니다.",
  OPENAI_CONTEXT_REVIEW_TRUNCATED: "문맥 검토 호출 한도에 따라 일부 긴 조항은 OpenAI 추가 검토에서 제외되었습니다.",
  OPENAI_CONTEXT_OUTPUT_REJECTED: "원문 인용이나 분류 검증을 통과하지 못한 OpenAI 후보는 결과에서 제외했습니다.",
  OPENAI_SUMMARY_FAILED: "OpenAI 핵심 요약을 완료하지 못해 결정론 요약을 표시합니다.",
  LLM_RATE_LIMITED: "OpenAI 호출 한도에 도달해 문맥 검토를 생략했습니다.",
  LLM_QUOTA_EXCEEDED: "OpenAI API 사용 한도로 문맥 검토를 생략했습니다.",
};

function renderSpan(text: string, span: [number, number], key: string): ReactNode {
  const [start, end] = span;
  if (start < 0 || end <= start || end > text.length) return text;
  return <>{text.slice(0, start)}<mark key={key}>{text.slice(start, end)}</mark>{text.slice(end)}</>;
}

function asClientError(reason: unknown, stage: ClientApiError["stage"]): ClientApiError {
  if (reason instanceof ClientApiError) return reason;
  return new ClientApiError(stage, "CLIENT_ERROR", "처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.", true);
}

function FailurePanel({ analysis, onRetry }: { analysis: Analysis; onRetry: () => void }) {
  return <section className="failure-panel" role="alert">
    <h2>분석을 완료하지 못했습니다</h2>
    <p>일시적인 오류일 수 있습니다. 기존 분석 ID로 상태를 다시 확인하거나 문서를 다시 업로드하세요.</p>
    <p><b>오류 코드:</b> {analysis.error_code ?? "ANALYSIS_FAILED"}</p>
    <p><b>재시도 가능:</b> {analysis.retryable ? "예" : "아니요 또는 수동 검토 필요"}</p>
    <button onClick={onRetry}>상태 다시 확인</button>
  </section>;
}

function FindingCard({ finding, analysisId }: { finding: Finding; analysisId: string }) {
  const explanation = finding.explanation;
  const page = finding.source.page_number ? ` · PDF ${finding.source.page_number}페이지` : "";
  const previews = finding.source.preview_status === "available" ? finding.source.preview_ids ?? [] : [];
  return <article className="finding">
    <header>
      <div><span className="tag">{strengthLabels[finding.rule_signal.signal_strength] ?? finding.rule_signal.signal_strength}</span><h3>{finding.clause ? `${finding.clause.label ?? `제${finding.clause.number}조`}${finding.clause.subclause_label ? ` · ${finding.clause.subclause_label}` : ""}${page} · ` : ""}{finding.rule_signal.rule_name ?? finding.rule_signal.category}</h3></div>
      <span className={`verification ${finding.verification.status}`}>{verificationLabels[finding.verification.status] ?? "근거 상태 확인 필요"}</span>
    </header>

    <p className="finding-summary">{finding.summary_sentence}</p>

    <section className="finding-source">
      <h4>실제 문서의 마스킹 원문 근거</h4>
      {previews.map(previewId => <img className="source-preview" key={previewId} src={sourcePreviewUrl(analysisId, previewId)} alt={`${finding.source.page_number ?? "문서"}페이지의 개인정보가 제거된 탐지 문구`} />)}
      {previews.length === 0 && <blockquote>{renderSpan(finding.source.masked_text, finding.source.match_span, `${finding.finding_id}-source`)}</blockquote>}
      {previews.length > 0 && <details className="text-source"><summary>마스킹 텍스트로 보기</summary><blockquote>{renderSpan(finding.source.masked_text, finding.source.match_span, `${finding.finding_id}-source`)}</blockquote></details>}
    </section>

    <section>
      <h4>확인할 질문</h4>
      <ul>{explanation.review_points.map(point => <li key={point}>{point}</li>)}</ul>
    </section>

    <details className="detail-block"><summary>상세 검토</summary>
      <div className="explanation-grid">
        <section><h4>왜 문제 후보인가</h4><p>{explanation.why_flagged}</p></section>
        <section><h4>예상되는 고객 영향</h4><p>{explanation.possible_impact}</p></section>
      </div>
      <section className="revision"><h4>검토용 대안 조항</h4><p>{explanation.suggested_revision}</p><small>{explanation.disclaimer}</small></section>
      <section><h4>법적 근거 후보</h4>
        {finding.evidence.length === 0 && <p className="muted">검증된 근거를 검색하지 못했습니다. 법령 원문과 시행일을 별도로 확인하세요.</p>}
        {finding.evidence.map(item => <div className="evidence" key={item.evidence_id}><b>{item.title}</b>{item.quoted_excerpt && <q>{item.quoted_excerpt}</q>}<small>{item.authority} · {item.status}{item.relevance_score !== undefined ? ` · 관련도 ${item.relevance_score}` : ""}</small>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer noopener">법령 원문 열기</a>}</div>)}
      </section>
      <h4>전문가용 검증 정보</h4>
      <dl>
        <div><dt>규칙 ID</dt><dd>{finding.rule_signal.rule_id}</dd></div>
        <div><dt>규칙 버전</dt><dd>{finding.rule_signal.rule_version ?? "미상"}</dd></div>
        <div><dt>corpus 버전</dt><dd>{finding.grounding?.corpus_version ?? "확인 불가"}</dd></div>
        <div><dt>근거 상태</dt><dd>{finding.grounding?.status ?? "확인 불가"}</dd></div>
      </dl>
      {(finding.verification.issues ?? []).map(issue => <p className="verification-issue" key={`${issue.code}-${issue.message}`}><b>{issue.code}</b> · {issue.message}</p>)}
    </details>
  </article>;
}

function CandidateCard({ candidate, analysisId }: { candidate: CandidateFinding; analysisId: string }) {
  const clause = candidate.clause.label ?? `제${candidate.clause.number}조`;
  const page = candidate.source.page_number ? ` · PDF ${candidate.source.page_number}페이지` : "";
  const previews = candidate.source.preview_status === "available" ? candidate.source.preview_ids ?? [] : [];
  const isOpenAI = candidate.review_method === "openai_context";
  return <article className="finding candidate">
    <header><div><span className="tag">{isOpenAI ? "AI 문맥 검토 후보" : "로컬 의미 검토 후보"} · {candidate.confidence}</span><h3>{clause}{candidate.clause.subclause_label ? ` · ${candidate.clause.subclause_label}` : ""}{page} · {candidate.name}</h3></div><span>규칙 미매핑</span></header>
    <p className="finding-summary">{candidate.summary_sentence}</p>
    <section className="finding-source"><h4>후보 근거</h4>{previews.map(previewId => <img className="source-preview" key={previewId} src={sourcePreviewUrl(analysisId, previewId)} alt={`${candidate.source.page_number ?? "문서"}페이지의 개인정보가 제거된 후보 문구`} />)}{previews.length === 0 && <blockquote>{candidate.source.masked_text}</blockquote>}</section>
    <section><h4>확인 질문</h4><ul>{candidate.review_questions.map(question => <li key={question}>{question}</li>)}</ul></section>
    <details className="detail-block"><summary>{isOpenAI ? "OpenAI 문맥 검토 상세" : "로컬 의미 모델 상세"}</summary>{isOpenAI ? <><p>{candidate.rationale}</p>{(candidate.counter_considerations ?? []).length > 0 && <p>반대 사정: {(candidate.counter_considerations ?? []).join(" · ")}</p>}<small>{candidate.model_id} · {candidate.model_revision}</small></> : <><p>유사도 {(candidate.similarity_score ?? 0).toFixed(3)}{candidate.similarity_margin !== undefined ? ` · 안전 예문 대비 ${candidate.similarity_margin.toFixed(3)}` : ""} · {candidate.model_id}</p><small>리비전 {candidate.model_revision}</small></>}</details>
    <small>이 항목은 결정론 규칙 탐지가 아닌 추가 검토 후보이며, 법률 판단이나 확정 신호가 아닙니다.</small>
  </article>;
}

/** Own upload, progress, grounded review, report export, and explicit deletion. */
export function AnalysisWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ClientApiError | null>(null);

  async function continuePolling(target: Analysis) {
    setBusy(true); setError(null); setAnalysis(target);
    try { setAnalysis(await waitForAnalysis(target)); }
    catch (reason) { setError(asClientError(reason, "poll")); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(null); setAnalysis(null);
    try {
      const created = await uploadAndAnalyze(file);
      setAnalysis(created);
      setAnalysis(await waitForAnalysis(created));
    } catch (reason) { setError(asClientError(reason, "upload")); }
    finally { setBusy(false); }
  }

  async function refresh() {
    if (!analysis) return;
    setBusy(true); setError(null);
    try {
      const current = await getAnalysis(analysis.id);
      if (current.status === "completed" || current.status === "failed") {
        setAnalysis(current);
        setBusy(false);
      } else {
        await continuePolling(current);
      }
    } catch (reason) { setError(asClientError(reason, "poll")); setBusy(false); }
  }

  async function remove() {
    if (!analysis) return;
    try {
      await deleteDocument(analysis.document_id);
      setAnalysis(null); setFile(null); setError(null);
    } catch (reason) { setError(asClientError(reason, "delete")); }
  }

  async function report() {
    if (!analysis) return;
    try { await downloadReport(analysis.id); }
    catch (reason) { setError(asClientError(reason, "report")); }
  }

  const progressState = analysis?.progress?.state ?? analysis?.status;
  const findings = analysis?.result?.findings ?? [];
  const candidateFindings = analysis?.result?.candidate_findings ?? [];

  return <main>
    <section className="hero">
      <div><p className="eyebrow">금융 계약서 Vertical AI 실험</p><h1>FinContract AI</h1><p>위험 신호와 확인 가능한 근거를 나란히 보여주는 계약 검토 보조 도구</p></div>
      <span className="notice">법률 판단이 아닌 검토 보조</span>
    </section>

    {!analysis && <section className="panel demo-guide" aria-labelledby="demo-guide-title">
      <div className="demo-guide-copy">
        <p className="eyebrow">처음 방문하셨나요?</p>
        <h2 id="demo-guide-title">실험 문서로 바로 확인해 보세요</h2>
        <p>FinContract AI는 금융 계약서에서 검토가 필요한 위험 신호를 탐색하는 실험용 서비스입니다. 제공된 가상 계약서 PDF 한 개를 업로드하면 탐지 조항, 확인 질문, 법적 근거 후보와 PDF 리포트를 확인할 수 있습니다.</p>
        <a className="demo-download" href="/demo/fincontract-ai-demo-data-v1.zip" download>실험용 계약서 11종 다운로드 <span>ZIP · 약 1.2MB</span></a>
        <small>실제 금융회사·상품·고객과 무관하며 개인정보를 포함하지 않는 가상 문서입니다.</small>
      </div>
      <ol className="demo-steps" aria-label="실험 서비스 체험 순서">
        <li><b>다운로드</b><span>실험 문서 ZIP을 내려받습니다.</span></li>
        <li><b>PDF 업로드</b><span>압축을 풀고 01번 문서를 선택합니다.</span></li>
        <li><b>결과 확인</b><span>검토 신호와 PDF 리포트를 확인합니다.</span></li>
      </ol>
    </section>}

    <nav className="stages" aria-label="분석 단계">
      {stageLabels.map((label, index) => <span key={label} className={analysis || index === 0 ? "active" : ""}>{index + 1}. {label}</span>)}
    </nav>

    <section className="panel">
      <h2>계약서 업로드</h2><p className="muted">TXT, PDF, DOCX · 최대 10MB · 원문은 분석 후 삭제할 수 있습니다.</p>
      <form onSubmit={submit}>
        <label className="drop"><input aria-label="계약서 파일" type="file" accept=".txt,.pdf,.docx" onChange={event => setFile(event.target.files?.[0] ?? null)} /><b>{file?.name ?? "파일을 선택하세요"}</b><span>마스킹 전 원문은 외부 모델이나 ChromaDB로 보내지 않습니다.</span></label>
        <div className="actions"><span className="muted">19개 규칙과 추가 의미 검토를 함께 실행합니다.</span><button disabled={!file || busy}>{busy ? `${statusLabels[progressState ?? "analyzing"] ?? "분석 중"}…` : "분석 시작"}</button></div>
      </form>
      {error && <section role="alert" className="error-panel"><h3>{error.message}</h3>{error.retryable && analysis && <button onClick={refresh}>상태 다시 확인</button>}<details><summary>기술 정보</summary><p>단계 {error.stage} · 코드 {error.code}{error.httpStatus ? ` · HTTP ${error.httpStatus}` : ""}</p></details></section>}
    </section>

    {analysis && <section aria-live="polite">
      <div className="panel summary">
        <div><span>상태</span><b>{statusLabels[progressState ?? analysis.status] ?? analysis.status}</b></div>
        <div><span>진행률</span><b>{analysis.progress?.percent ?? (analysis.status === "completed" ? 100 : 0)}%</b></div>
        <div><span>결과</span><b>{dispositionLabels[analysis.disposition] ?? analysis.disposition}</b></div>
        <div><span>검토 신호</span><b>{findings.length}</b></div>
        <div><span>추가 검토 후보</span><b>{candidateFindings.length}</b></div>
        {analysis.status === "completed" && <button className="report-link" onClick={report}>PDF 리포트</button>}
        <button className="secondary" onClick={remove}>원문·결과 삭제</button>
      </div>
      {analysis.result?.summary?.headline && <section className="panel document-summary"><h2>핵심 요약</h2>{(analysis.result.summary.lines?.length ? analysis.result.summary.lines : [analysis.result.summary.headline]).map((line, index) => <p key={`${index}-${line}`}>{line}</p>)}</section>}
      {analysis.status === "failed" && <FailurePanel analysis={analysis} onRetry={refresh} />}
      {analysis.disposition === "no_signal" && <section className="no-signal"><h2>검토 신호 없음</h2><p>현재 19개 규칙과 추가 의미 검토에서 위험 신호가 탐지되지 않았습니다. 이는 계약의 안전성이나 적법성을 보장하지 않습니다.</p></section>}
      {(analysis.result?.warnings ?? []).map(warning => <p className="warning" key={warning}>{warningLabels[warning] ?? warning}</p>)}
      {findings.map(finding => <FindingCard finding={finding} analysisId={analysis.id} key={finding.finding_id} />)}
      {candidateFindings.length > 0 && <section className="panel"><h2>추가 의미 검토 후보</h2><p className="muted">로컬 의미 모델과 선택적 OpenAI 문맥 검토가 제안한 후보이며, 같은 조문·유형의 규칙 탐지와 중복되는 항목은 제외합니다.</p>{candidateFindings.map(candidate => <CandidateCard candidate={candidate} analysisId={analysis.id} key={candidate.candidate_id} />)}</section>}
      <section className="panel limitations"><h2>데이터 제공 범위</h2><p><b>원문 근거</b>는 탐지된 조항의 개인정보 제거 조각만 표시하며 문서 전문은 브라우저로 전송하지 않습니다.</p><p><b>은행 비교</b>는 검증된 공개·허가 비교 데이터가 아직 없어 순위·추천·비교 결과를 제공하지 않습니다.</p><p><b>리포트</b>는 계약 검토 보조 자료이며, 법률 판단이나 상품 추천이 아닙니다.</p></section>
    </section>}
  </main>;
}
