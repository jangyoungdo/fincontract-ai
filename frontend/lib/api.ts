export type ApiStage = "upload" | "analysis_create" | "poll" | "report" | "delete";

export class ClientApiError extends Error {
  constructor(
    public readonly stage: ApiStage,
    public readonly code: string,
    message: string,
    public readonly retryable: boolean,
    public readonly httpStatus?: number,
  ) {
    super(message);
    this.name = "ClientApiError";
  }
}

export type FindingExplanation = {
  why_flagged: string;
  possible_impact: string;
  review_points: string[];
  suggested_revision: string;
  revision_points?: string[];
  example_clause?: string;
  guidance_version?: string;
  disclaimer: string;
};

export type Evidence = {
  evidence_id: string;
  title: string;
  status: string;
  authority: string;
  source_url?: string;
  quoted_excerpt?: string;
  relevance_score?: number;
  manifest_version?: string;
};

export type Finding = {
  finding_id: string;
  summary_sentence: string;
  source: {
    masked_text: string;
    match_span: [number, number];
    page_number?: number | null;
    preview_status?: "available" | "text_only" | "unavailable";
    preview_ids?: string[];
  };
  rule_signal: {
    rule_id: string;
    rule_version?: string;
    rule_name: string;
    category: string;
    matched_excerpt: string;
    risk_span?: [number, number];
    matched_elements?: Array<{ label: string; excerpt: string; span: [number, number] }>;
    match_span?: [number, number];
    signal_strength: string;
    rationale: string;
  };
  explanation: FindingExplanation;
  evidence: Evidence[];
  legal_basis_candidates?: Evidence[];
  grounding?: { status: string; retrieved_count: number; corpus_version: string };
  assessment?: {
    risk_level?: string;
    applicability?: string;
    summary: string;
    rationale?: string;
    counter_considerations: string[];
    review_questions: string[];
    cited_evidence_ids?: string[];
  } | null;
  verification: {
    status: string;
    issues?: Array<{ code: string; message: string }>;
    attempts?: number;
  };
  clause?: { number: number | null; label?: string; subclause_label?: string; section_type?: string; section_id?: string; char_start: number; char_end: number };
};

export type CandidateFinding = {
  candidate_id: string;
  category: string;
  name: string;
  status: "semantic_review_candidate";
  review_method?: "local_e5" | "openai_context";
  confidence: string;
  similarity_score?: number;
  similarity_margin?: number;
  model_id: string;
  model_revision: string;
  matched_prototype_ids: string[];
  review_questions: string[];
  rationale?: string;
  counter_considerations?: string[];
  summary_sentence: string;
  source: {
    masked_text: string;
    match_span?: [number, number];
    page_number?: number | null;
    preview_status?: "available" | "text_only" | "unavailable";
    preview_ids?: string[];
  };
  clause: { number: number | null; label?: string; subclause_label?: string | null; section_type?: string; section_id?: string; char_start: number; char_end: number };
};

export type Analysis = {
  id: string;
  document_id: string;
  status: string;
  disposition: string;
  experiment_arm: string;
  error_code?: string | null;
  retryable?: boolean | null;
  result?: {
    findings: Finding[];
    candidate_findings?: CandidateFinding[];
    warnings: string[];
    clause_count: number;
    result_schema_version?: string;
    summary?: {
      headline: string;
      lines?: string[];
      top_categories: string[];
      generation?: {
        method: "openai" | "deterministic_fallback";
        model?: string;
        prompt_version?: string;
        response_id?: string | null;
      };
    };
    versions?: { ruleset?: string; corpus?: string };
    document?: { pii_types: string[]; pii_replacement_count: number; page_count?: number; source_type?: string };
  };
  progress?: { state: string; percent: number };
};

const API_BASE = "/api/v1";

const ERROR_MESSAGES: Record<string, string> = {
  API_UNREACHABLE: "분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.",
  PDF_ENCRYPTED: "암호화된 PDF는 처리할 수 없습니다. 암호를 해제한 사본을 업로드하세요.",
  PDF_PAGE_LIMIT: "PDF가 페이지 제한을 초과했습니다. 문서를 나누어 업로드하세요.",
  FILE_TOO_LARGE: "파일이 10MB 제한을 초과했습니다. 파일 크기를 줄여 다시 업로드하세요.",
  OCR_REQUIRED: "문자 인식이 필요한 PDF입니다. 검색 가능한 PDF로 변환한 뒤 다시 업로드하세요.",
  OCR_LOW_CONFIDENCE: "PDF 문자 인식 품질이 낮아 안전하게 분석할 수 없습니다. 더 선명한 파일을 사용하세요.",
  OCR_TIMEOUT: "PDF 문자 인식 시간이 초과되었습니다. 문서를 나누어 다시 시도하세요.",
  OCR_PIXEL_LIMIT: "PDF 이미지 크기가 처리 제한을 초과했습니다. 해상도를 낮추거나 문서를 나누세요.",
  OCR_UNAVAILABLE: "문자 인식 기능을 현재 사용할 수 없습니다. 잠시 후 다시 시도하세요.",
  ANALYSIS_RETRYING: "일시적인 분석 오류로 자동 재시도 중입니다.",
  ANALYSIS_QUEUE_UNAVAILABLE: "분석 대기열을 현재 사용할 수 없습니다. 잠시 후 다시 시도하세요.",
  ANALYSIS_TIMEOUT: "분석이 120초 안에 끝나지 않았습니다. 분석 ID는 유지되므로 상태를 다시 확인하세요.",
  DOCUMENT_NOT_FOUND: "문서를 찾을 수 없습니다. 보존 기간 만료 또는 삭제 여부를 확인하세요.",
  ANALYSIS_FAILED: "분석을 완료하지 못했습니다. 상태를 다시 확인하거나 문서를 다시 업로드하세요.",
};

const STAGE_FALLBACKS: Record<ApiStage, string> = {
  upload: "문서를 업로드하지 못했습니다. 파일 형식과 크기를 확인하세요.",
  analysis_create: "분석을 시작하지 못했습니다. 잠시 후 다시 시도하세요.",
  poll: "분석 상태를 확인하지 못했습니다. 잠시 후 상태를 다시 확인하세요.",
  report: "PDF 리포트를 내려받지 못했습니다. 분석 완료 상태를 확인하세요.",
  delete: "문서를 삭제하지 못했습니다. 잠시 후 다시 시도하세요.",
};

type ErrorPayload = { detail?: unknown; error_code?: unknown; code?: unknown; retryable?: unknown };

function inferCode(detail: string, status: number): string {
  const stablePrefix = detail.match(/^([A-Z][A-Z0-9_]+):/);
  if (stablePrefix) return stablePrefix[1];
  const normalized = detail.toLowerCase();
  if (normalized.includes("암호") || normalized.includes("encrypted")) return "PDF_ENCRYPTED";
  if (normalized.includes("페이지") && normalized.includes("제한")) return "PDF_PAGE_LIMIT";
  if (normalized.includes("10mb") || normalized.includes("too large") || normalized.includes("크기 제한")) return "FILE_TOO_LARGE";
  if (normalized.includes("ocr")) return "OCR_REQUIRED";
  if (status === 502 || status === 503 || status === 504) return "API_UNREACHABLE";
  return "API_ERROR";
}

async function apiError(response: Response, stage: ApiStage): Promise<ClientApiError> {
  let payload: ErrorPayload = {};
  try { payload = await response.json() as ErrorPayload; } catch { /* A safe fallback hides raw server output. */ }
  const detail = typeof payload.detail === "string" ? payload.detail : "";
  const codeValue = payload.error_code ?? payload.code;
  const code = typeof codeValue === "string" ? codeValue : inferCode(detail, response.status);
  const retryable = typeof payload.retryable === "boolean"
    ? payload.retryable
    : response.status >= 500 || response.status === 408 || response.status === 429;
  return new ClientApiError(stage, code, ERROR_MESSAGES[code] ?? STAGE_FALLBACKS[stage], retryable, response.status);
}

async function safeFetch(input: RequestInfo | URL, init: RequestInit, stage: ApiStage): Promise<Response> {
  try {
    const response = await fetch(input, init);
    if (!response.ok) throw await apiError(response, stage);
    return response;
  } catch (reason) {
    if (reason instanceof ClientApiError) throw reason;
    throw new ClientApiError(stage, "API_UNREACHABLE", ERROR_MESSAGES.API_UNREACHABLE, true);
  }
}

/** Build the same-origin PDF endpoint without placing document content in the URL. */
export function reportPdfUrl(analysisId: string): string {
  return `${API_BASE}/analyses/${encodeURIComponent(analysisId)}/report.pdf`;
}

export function sourcePreviewUrl(analysisId: string, previewId: string): string {
  return `${API_BASE}/analyses/${encodeURIComponent(analysisId)}/source-previews/${encodeURIComponent(previewId)}.png`;
}

/** Upload one validated file, then create the single production analysis. */
export async function uploadAndAnalyze(file: File): Promise<Analysis> {
  const form = new FormData();
  form.append("file", file);
  const uploaded = await safeFetch(`${API_BASE}/documents`, { method: "POST", body: form }, "upload");
  const document = await uploaded.json() as { id: string };
  const analyzed = await safeFetch(
    `${API_BASE}/documents/${encodeURIComponent(document.id)}/analyses`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    },
    "analysis_create",
  );
  return analyzed.json() as Promise<Analysis>;
}

/** Fetch one persisted analysis without restarting the analysis job. */
export async function getAnalysis(analysisId: string): Promise<Analysis> {
  const response = await safeFetch(
    `${API_BASE}/analyses/${encodeURIComponent(analysisId)}`,
    { method: "GET", cache: "no-store" },
    "poll",
  );
  return response.json() as Promise<Analysis>;
}

/** Poll queued, analyzing, and retrying work until a terminal state or 120-second limit. */
export async function waitForAnalysis(
  analysis: Analysis,
  options: { maxAttempts?: number; pollIntervalMs?: number } = {},
): Promise<Analysis> {
  const maxAttempts = options.maxAttempts ?? 120;
  const pollIntervalMs = options.pollIntervalMs ?? 1000;
  let current = analysis;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (current.status === "completed" || current.status === "failed") return current;
    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
    current = await getAnalysis(current.id);
  }
  throw new ClientApiError("poll", "ANALYSIS_TIMEOUT", ERROR_MESSAGES.ANALYSIS_TIMEOUT, true);
}

/** Download the audited report through the same-origin proxy and surface report-stage errors. */
export async function downloadReport(analysisId: string): Promise<void> {
  const response = await safeFetch(reportPdfUrl(analysisId), { method: "GET" }, "report");
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = `fincontract-${analysisId}.pdf`;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}

/** Request encrypted-file deletion and metadata tombstoning for one document. */
export async function deleteDocument(documentId: string): Promise<void> {
  await safeFetch(`${API_BASE}/documents/${encodeURIComponent(documentId)}`, { method: "DELETE" }, "delete");
}
