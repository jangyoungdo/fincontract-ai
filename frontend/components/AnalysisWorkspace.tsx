"use client";

import { FormEvent, ReactNode, useState } from "react";
import {
  Analysis,
  BankComparison,
  ClientApiError,
  Finding,
  PRODUCT_TYPES,
  deleteDocument,
  downloadReport,
  getAnalysis,
  getBankComparison,
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

function renderSpan(text: string, span: [number, number], key: string): ReactNode {
  const [start, end] = span;
  if (start < 0 || end <= start || end > text.length) return text;
  return <>{text.slice(0, start)}<mark key={key}>{text.slice(start, end)}</mark>{text.slice(end)}</>;
}

function renderMaskedDocument(text: string, findings: Finding[]): ReactNode[] {
  const ranges = findings
    .filter(finding => finding.clause)
    .map(finding => ({
      start: finding.clause!.char_start + finding.source.match_span[0],
      end: finding.clause!.char_start + finding.source.match_span[1],
      id: finding.finding_id,
    }))
    .filter(range => range.start >= 0 && range.end > range.start && range.end <= text.length)
    .sort((left, right) => left.start - right.start);
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start < cursor) continue;
    nodes.push(text.slice(cursor, range.start));
    nodes.push(<mark key={range.id}>{text.slice(range.start, range.end)}</mark>);
    cursor = range.end;
  }
  nodes.push(text.slice(cursor));
  return nodes;
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

function FindingCard({ finding }: { finding: Finding }) {
  const explanation = finding.explanation;
  return <article className="finding">
    <header>
      <div><span className="tag">{strengthLabels[finding.rule_signal.signal_strength] ?? finding.rule_signal.signal_strength}</span><h3>{finding.clause ? `제${finding.clause.number}조 · ` : ""}{finding.rule_signal.rule_name ?? finding.rule_signal.category}</h3></div>
      <span>검증 {finding.verification.status}</span>
    </header>

    <section className="finding-source">
      <h4>정확히 탐지된 문구</h4>
      <blockquote>{renderSpan(finding.source.masked_text, finding.source.match_span, `${finding.finding_id}-source`)}</blockquote>
    </section>

    <div className="explanation-grid">
      <section><h4>왜 문제 후보인가</h4><p>{explanation.why_flagged}</p></section>
      <section><h4>예상되는 고객 영향</h4><p>{explanation.possible_impact}</p></section>
    </div>

    <section>
      <h4>반대 사정과 확인 조건</h4>
      <ul>{explanation.review_points.map(point => <li key={point}>{point}</li>)}</ul>
    </section>

    <section className="revision">
      <h4>검토용 대안 조항</h4>
      <p>{explanation.suggested_revision}</p>
      <small>{explanation.disclaimer}</small>
    </section>

    <section>
      <h4>법적 근거 후보</h4>
      {finding.evidence.length === 0 && <p className="muted">검증된 근거를 검색하지 못했습니다. 법령 원문과 시행일을 별도로 확인하세요.</p>}
      {finding.evidence.map(item => <div className="evidence" key={item.evidence_id}>
        <b>{item.title}</b>
        {item.quoted_excerpt && <q>{item.quoted_excerpt}</q>}
        <small>{item.authority} · {item.status}{item.relevance_score !== undefined ? ` · 관련도 ${item.relevance_score}` : ""}</small>
        {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer noopener">법령 원문 열기</a>}
      </div>)}
    </section>

    {finding.assessment && <details className="detail-block">
      <summary>AI 보충 검토 ({finding.assessment.risk_level ?? "mock"})</summary>
      <p>{finding.assessment.summary}</p>
      {finding.assessment.rationale && <p>{finding.assessment.rationale}</p>}
      <h5>반대 고려사항</h5><ul>{finding.assessment.counter_considerations.map(item => <li key={item}>{item}</li>)}</ul>
      <h5>추가 확인 질문</h5><ul>{finding.assessment.review_questions.map(item => <li key={item}>{item}</li>)}</ul>
    </details>}

    <details className="detail-block">
      <summary>전문가용 검증 상세</summary>
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

function BankComparisonPanel({
  comparison,
  busy,
  error,
  onCompare,
}: {
  comparison: BankComparison | null;
  busy: boolean;
  error: ClientApiError | null;
  onCompare: () => void;
}) {
  return <section className="panel comparison-panel">
    <h2>타은행 비교</h2>
    <p className="muted">규칙 기반 정성 비교이며 법률 자문이나 상품 추천이 아닙니다. 검증된 동종 은행 자료가 있을 때만 결과를 표시합니다.</p>
    {!comparison && <button onClick={onCompare} disabled={busy}>{busy ? "비교 중…" : "타은행과 비교하기"}</button>}
    {error && <section role="alert" className="error-panel">
      <h3>{error.message}</h3>
      {error.retryable && <button onClick={onCompare}>다시 시도</button>}
    </section>}
    {comparison?.comparison_status === "insufficient_peer_data" && (
      <p className="muted">동종 상품을 등록한 은행이 아직 충분하지 않아(현재 {comparison.peer_bank_count}곳) 비교를 제공하지 않습니다.</p>
    )}
    {comparison?.comparison_status === "ready" && <>
      <p className="muted">{comparison.generated_note} · 동종 은행 {comparison.peer_bank_count}곳과 비교 · corpus {comparison.corpus_version}</p>
      <div className="comparison-grid">
        <div className="comparison-pros">
          <h3>장점</h3>
          {comparison.pros.length === 0 && <p className="muted">동종 대비 뚜렷한 장점 신호가 없습니다.</p>}
          {comparison.pros.map(item => <div className="comparison-item" key={item.rule_id}>
            <b>{item.rule_name}</b>
            <p>{item.explanation}</p>
            <span className="comparison-rate">동종 은행 {item.peer_bank_count}곳 중 {Math.round(item.peer_match_rate * item.peer_bank_count)}곳 해당</span>
          </div>)}
        </div>
        <div className="comparison-cons">
          <h3>단점</h3>
          {comparison.cons.length === 0 && <p className="muted">동종 대비 뚜렷한 단점 신호가 없습니다.</p>}
          {comparison.cons.map(item => <div className="comparison-item" key={item.rule_id}>
            <b>{item.rule_name}</b>
            <p>{item.explanation}</p>
            <span className="comparison-rate">동종 은행 {item.peer_bank_count}곳 중 {Math.round(item.peer_match_rate * item.peer_bank_count)}곳 해당</span>
          </div>)}
        </div>
      </div>
    </>}
  </section>;
}

/** Own upload, progress, grounded review, report export, and explicit deletion. */
export function AnalysisWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [arm, setArm] = useState<"A" | "D">("D");
  const [bankName, setBankName] = useState("");
  const [productType, setProductType] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ClientApiError | null>(null);
  const [comparison, setComparison] = useState<BankComparison | null>(null);
  const [comparisonBusy, setComparisonBusy] = useState(false);
  const [comparisonError, setComparisonError] = useState<ClientApiError | null>(null);

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
    setComparison(null); setComparisonError(null);
    try {
      const created = await uploadAndAnalyze(file, arm, bankName, productType);
      setAnalysis(created);
      setAnalysis(await waitForAnalysis(created));
    } catch (reason) { setError(asClientError(reason, "upload")); }
    finally { setBusy(false); }
  }

  async function compareBanks() {
    if (!analysis) return;
    setComparisonBusy(true); setComparisonError(null);
    try { setComparison(await getBankComparison(analysis.id)); }
    catch (reason) { setComparisonError(asClientError(reason, "compare")); }
    finally { setComparisonBusy(false); }
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
      setComparison(null); setComparisonError(null);
    } catch (reason) { setError(asClientError(reason, "delete")); }
  }

  async function report() {
    if (!analysis) return;
    try { await downloadReport(analysis.id); }
    catch (reason) { setError(asClientError(reason, "report")); }
  }

  const progressState = analysis?.progress?.state ?? analysis?.status;
  const findings = analysis?.result?.findings ?? [];

  return <main>
    <section className="hero">
      <div><p className="eyebrow">금융 계약서 Vertical AI 실험</p><h1>FinContract AI</h1><p>위험 신호와 확인 가능한 근거를 나란히 보여주는 계약 검토 보조 도구</p></div>
      <span className="notice">법률 판단이 아닌 검토 보조</span>
    </section>

    <nav className="stages" aria-label="분석 단계">
      {stageLabels.map((label, index) => <span key={label} className={analysis || index === 0 ? "active" : ""}>{index + 1}. {label}</span>)}
    </nav>

    <section className="panel">
      <h2>계약서 업로드</h2><p className="muted">TXT, PDF, DOCX · 최대 10MB · 원문은 분석 후 삭제할 수 있습니다.</p>
      <form onSubmit={submit}>
        <label className="drop"><input aria-label="계약서 파일" type="file" accept=".txt,.pdf,.docx" onChange={event => setFile(event.target.files?.[0] ?? null)} /><b>{file?.name ?? "파일을 선택하세요"}</b><span>마스킹 전 원문은 외부 모델이나 ChromaDB로 보내지 않습니다.</span></label>
        <div className="tagging-fields">
          <label>은행명(선택) <input aria-label="은행명" type="text" placeholder="예: 우리은행" value={bankName} onChange={event => setBankName(event.target.value)} /></label>
          <label>상품유형(선택) <select aria-label="상품유형" value={productType} onChange={event => setProductType(event.target.value)}>
            <option value="">선택 안 함</option>
            {Object.entries(PRODUCT_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        </div>
        <p className="muted">은행명과 상품유형을 입력하면 분석 완료 후 타은행과 비교할 수 있습니다.</p>
        <div className="actions"><label>실험군 <select value={arm} onChange={event => setArm(event.target.value as "A" | "D")}><option value="A">A · 규칙 기준선</option><option value="D">D · mock 분석·검증</option></select></label><button disabled={!file || busy}>{busy ? `${statusLabels[progressState ?? "analyzing"] ?? "분석 중"}…` : "분석 시작"}</button></div>
      </form>
      {error && <section role="alert" className="error-panel"><h3>{error.message}</h3>{error.retryable && analysis && <button onClick={refresh}>상태 다시 확인</button>}<details><summary>기술 정보</summary><p>단계 {error.stage} · 코드 {error.code}{error.httpStatus ? ` · HTTP ${error.httpStatus}` : ""}</p></details></section>}
    </section>

    {analysis && <section aria-live="polite">
      <div className="panel summary">
        <div><span>상태</span><b>{statusLabels[progressState ?? analysis.status] ?? analysis.status}</b></div>
        <div><span>진행률</span><b>{analysis.progress?.percent ?? (analysis.status === "completed" ? 100 : 0)}%</b></div>
        <div><span>결과</span><b>{dispositionLabels[analysis.disposition] ?? analysis.disposition}</b></div>
        <div><span>검토 신호</span><b>{findings.length}</b></div>
        {analysis.status === "completed" && <button className="report-link" onClick={report}>PDF 리포트</button>}
        <button className="secondary" onClick={remove}>원문·결과 삭제</button>
      </div>
      {analysis.status === "failed" && <FailurePanel analysis={analysis} onRetry={refresh} />}
      {analysis.disposition === "no_signal" && <section className="no-signal"><h2>실험 규칙 신호 없음</h2><p>현재 8개 실험 규칙에서 위험 신호가 탐지되지 않았습니다. 이는 계약의 안전성이나 적법성을 보장하지 않습니다.</p></section>}
      {(analysis.result?.warnings ?? []).map(warning => <p className="warning" key={warning}>{warning}</p>)}
      {analysis.result?.document?.masked_text && <section className="panel source-viewer"><h2>마스킹된 전체 문서</h2><p className="muted">개인정보 치환 {analysis.result.document.pii_replacement_count}건 · 실제 탐지 문구를 강조 표시합니다.</p><pre>{renderMaskedDocument(analysis.result.document.masked_text, findings)}</pre></section>}
      {findings.map(finding => <FindingCard finding={finding} key={finding.finding_id} />)}
      {analysis.status === "completed" && <BankComparisonPanel
        comparison={comparison}
        busy={comparisonBusy}
        error={comparisonError}
        onCompare={compareBanks}
      />}
      <section className="panel limitations"><h2>데이터 제공 범위</h2><p><b>원문 뷰어</b>는 개인정보를 치환한 전체 텍스트만 표시합니다. 마스킹 전 텍스트는 화면·검색·외부 모델로 전송하지 않습니다.</p><p><b>리포트</b>는 계약 검토 보조 자료이며, 법률 판단이나 상품 추천이 아닙니다.</p></section>
    </section>}
    {!analysis && <section className="panel limitations"><h2>타은행 비교</h2><p>은행명과 상품유형을 입력해 분석하면, 검증된 동종 은행 자료가 있을 때 장단점 비교를 제공합니다. 검증된 자료가 없는 경우 순위나 추천은 표시하지 않습니다.</p></section>}
  </main>;
}
