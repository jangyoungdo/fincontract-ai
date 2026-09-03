"""Versioned, deterministic drafting guidance for rule findings."""

from __future__ import annotations

from typing import Any

GUIDANCE_VERSION = "revision-guidance-v0.1.0"

# (change point 1, change point 2, example clause). These reviewed templates
# never infer contract-specific dates, amounts, institutions, or product terms.
GUIDANCE: dict[str, tuple[str, str, str]] = {
    "R01_EXCESSIVE_LIQUIDATED_DAMAGES": (
        "고객 책임을 실제 발생하고 객관적으로 입증된 직접 손해와 연결합니다.",
        "산정 기준과 합리적인 부담 한도를 조항에 명시합니다.",
        "고객의 손해배상 책임은 고객의 귀책으로 실제 발생하고 객관적으로 입증된 직접 손해의 합리적인 범위로 한정합니다.",
    ),
    "R02_UNFAIR_TERMINATION": (
        "해지 사유를 구체적이고 중대한 의무 위반으로 한정합니다.",
        "사전 통지와 합리적인 시정 기회를 보장합니다.",
        "회사는 고객의 중대한 의무 위반이 있는 경우 그 사유를 서면으로 통지하고 합리적인 시정기간을 부여한 후, 시정되지 않은 때에 계약을 해지할 수 있습니다.",
    ),
    "R03_LIMITATION_OF_LIABILITY": (
        "법령상 배제할 수 없는 사업자 책임을 보존합니다.",
        "고의 또는 중대한 과실로 인한 책임은 면책 범위에서 제외합니다.",
        "회사는 관련 법령상 배제할 수 없는 책임과 회사의 고의 또는 중대한 과실로 발생한 손해에 대한 책임을 부담합니다.",
    ),
    "R04_UNILATERAL_CHANGE": (
        "변경 사유와 적용 범위를 객관적으로 한정합니다.",
        "사전 개별 통지, 거절·종료 선택권과 장래 적용 원칙을 함께 둡니다.",
        "회사는 객관적으로 정한 사유가 발생한 경우에만 계약 조건을 변경할 수 있으며, 불리한 변경은 사전에 고객에게 개별 통지하고 고객에게 변경 거절 또는 계약 종료의 선택권을 부여한 뒤 장래에 적용합니다.",
    ),
    "R05_ACCELERATION": (
        "기한의 이익 상실 사유를 중대한 채무불이행으로 구체화합니다.",
        "서면 통지와 합리적인 시정기간을 먼저 제공합니다.",
        "고객이 중대한 채무를 이행하지 않은 경우 회사는 그 사유를 서면으로 통지하고 합리적인 시정기간을 부여하며, 그 기간에도 시정되지 않은 때에 기한의 이익 상실을 통지할 수 있습니다.",
    ),
    "R06_TRANSFER_OF_RIGHTS": (
        "이전 대상, 사유와 고객에게 미치는 효과를 구체적으로 알립니다.",
        "법령 또는 계약상 필요한 고객 동의 절차를 보장합니다.",
        "회사가 계약상 지위를 제3자에게 이전하려는 경우 이전 대상·사유 및 고객에게 미치는 효과를 사전에 통지하고, 관련 법령 또는 계약에 따라 필요한 고객의 동의를 받습니다.",
    ),
    "R07_AUTOMATIC_RENEWAL": (
        "갱신 예정일, 변경 조건과 거절 기한을 사전에 알립니다.",
        "고객이 쉽게 이용할 수 있는 갱신 거절 절차를 제공합니다.",
        "회사는 갱신 예정일 전에 갱신 조건과 거절 기한·방법을 고객에게 개별 통지하며, 고객은 안내된 간편한 절차를 통해 갱신을 거절할 수 있습니다.",
    ),
    "R08_EXCLUSIVE_JURISDICTION": (
        "사업자 소재지 법원만을 전속 관할로 지정하지 않습니다.",
        "법정 관할과 고객 주소지 관할 선택 가능성을 보존합니다.",
        "계약과 관련한 분쟁은 민사소송법 등 관련 법령에서 정한 관할법원에 제기할 수 있으며, 고객의 법정 관할 선택권을 제한하지 않습니다.",
    ),
    "R09_EXCESSIVE_FEES_OR_RATE": (
        "수수료와 가산금리의 산정 기준을 구체적으로 공개합니다.",
        "실제 발생·증빙 가능한 비용 및 합리적인 상한과 연결합니다.",
        "고객이 부담하는 수수료 또는 가산금리는 사전에 공개된 객관적 산정 기준에 따라 계산하고, 실제 발생하여 증빙할 수 있는 합리적인 비용 범위를 초과하지 않도록 합니다.",
    ),
    "R10_TYING_OR_ANCILLARY_TRANSACTION": (
        "부수 상품 가입 여부를 고객의 자율 선택으로 둡니다.",
        "거절하더라도 본 계약의 필수 조건에 불이익이 없도록 분리합니다.",
        "신용카드·보험 등 부수 상품의 가입과 이용은 고객이 자율적으로 선택하며, 이를 거절했다는 이유만으로 본 계약의 필수 조건에 불이익을 주지 않습니다.",
    ),
    "R11_DEEMED_CONSENT": (
        "침묵, 무응답 또는 계속 이용만으로 동의를 간주하지 않습니다.",
        "중요한 불이익 변경에는 별도의 명시적 의사표시를 받습니다.",
        "고객의 침묵·무응답 또는 계속 이용만으로 동의를 간주하지 않으며, 고객에게 중요한 불이익이 발생하는 변경은 별도의 명시적 동의를 받아 적용합니다.",
    ),
    "R12_RETROACTIVE_DISADVANTAGE": (
        "이미 적용된 혜택을 사후에 소급하여 취소하지 않습니다.",
        "불이익 변경은 사전 통지 후 장래에만 적용하고 선택권을 제공합니다.",
        "우대조건이나 혜택의 불리한 변경은 고객에게 사전 통지한 뒤 장래에만 적용하며, 이미 적용된 혜택을 소급하여 취소하지 않습니다.",
    ),
    "R13_ADDITIONAL_COLLATERAL_OR_GUARANTEE": (
        "추가 담보 요구 사유와 평가 기준을 객관적으로 한정합니다.",
        "요구 범위, 통지 방법과 고객의 대응 절차를 명시합니다.",
        "회사는 객관적으로 정한 담보가치 변동 사유가 발생한 경우에만 필요한 범위에서 추가 담보를 요청할 수 있으며, 그 사유·평가기준·요구 범위와 고객의 대응 절차를 사전에 안내합니다.",
    ),
    "R14_EVIDENCE_MONOPOLY_AND_OBJECTION_LIMIT": (
        "사업자 기록을 유일하거나 최종적인 증거로 확정하지 않습니다.",
        "고객의 자료 열람, 반증과 이의제기 절차를 보장합니다.",
        "회사의 기록은 거래 내용을 확인하기 위한 자료 중 하나로 활용하며, 고객은 관련 자료를 열람하고 다른 자료로 반증하거나 정해진 절차에 따라 이의를 제기할 수 있습니다.",
    ),
    "R15_UNFAIR_COST_SHIFTING": (
        "비용 발생 원인과 각 당사자의 귀책을 구분합니다.",
        "실제 발생하고 객관적으로 입증된 합리적 비용으로 한정합니다.",
        "계약 이행 과정에서 발생한 비용은 각 당사자의 귀책과 관련 법령에 따라 부담하며, 고객 부담분은 실제 발생하고 객관적으로 입증된 합리적인 비용으로 한정합니다.",
    ),
    "R16_BROAD_DATA_USE_OR_THIRD_PARTY_SHARING": (
        "이용 정보, 목적, 제공받는 자와 보유기간을 구체화합니다.",
        "법적 근거가 없는 제3자 제공에는 필요한 별도 동의를 받습니다.",
        "회사는 명시한 목적에 필요한 최소한의 개인정보만 이용하며, 제3자 제공 시 제공 항목·목적·제공받는 자·보유기간을 구체적으로 알리고 관련 법령에 따라 필요한 별도 동의를 받습니다.",
    ),
    "R17_DEEMED_OR_INADEQUATE_NOTICE": (
        "중요 통지는 고객이 확인할 수 있는 방법으로 개별 전달합니다.",
        "반송 또는 미도달 시 재통지 등 보완 절차를 둡니다.",
        "계약상 권리나 기한에 영향을 주는 중요 통지는 고객이 확인할 수 있는 방법으로 개별 전달하며, 반송 또는 미도달이 확인된 경우 재통지 등 합리적인 보완 절차를 진행합니다.",
    ),
    "R18_CUSTOMER_RIGHTS_RESTRICTION": (
        "해지·이의제기 등 고객의 법령상 권리를 원칙적으로 보존합니다.",
        "제한이 필요한 경우 사유·범위·기간과 이의제기 절차를 구체화합니다.",
        "고객은 관련 법령과 이 계약에서 정한 절차에 따라 해지·이의제기 등 자신의 권리를 행사할 수 있습니다. 권리 행사가 제한되는 경우에는 그 사유·범위·기간을 구체적으로 명시하고 고객에게 이의제기 및 구제 절차를 안내합니다.",
    ),
    "R19_REPRESENTATIVE_OR_GUARANTOR_BURDEN": (
        "보증 또는 대리 책임의 대상, 최고액과 기간을 구체화합니다.",
        "책임 내용을 별도로 설명하고 당사자의 명시적 동의를 받습니다.",
        "보증인 또는 대리인의 책임은 별도로 명시한 채무의 범위·최고액·기간으로 한정하며, 회사는 해당 책임 내용을 사전에 설명하고 당사자의 명시적 동의를 받습니다.",
    ),
}

_RIGHT_NAMES = {
    "이의": "이의제기권",
    "이의제기": "이의제기권",
    "항변권": "항변권",
    "상계권": "상계권",
    "해지": "해지권",
    "해지권": "해지권",
    "철회": "철회권",
    "취소권": "취소권",
    "민원": "민원 제기 권리",
    "손해배상청구": "손해배상청구권",
    "다투": "다툴 권리",
    "다툴": "다툴 권리",
    "소송": "소송 제기 권리",
}


def _object_marker(word: str) -> str:
    """Return the Korean object marker for the final Hangul syllable."""
    final = ord(word[-1]) - 0xAC00
    return "을" if 0 <= final <= 11171 and final % 28 else "를"


def enrich_revision_guidance(
    rule_id: str,
    explanation: dict[str, Any],
    matched_elements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a copy with drafting guidance while preserving legacy fields."""
    enriched = dict(explanation)
    template = GUIDANCE.get(rule_id)
    if template is None:
        return enriched
    point_one, point_two, example_clause = template
    if rule_id == "R18_CUSTOMER_RIGHTS_RESTRICTION" and matched_elements:
        detected = str(matched_elements[0].get("excerpt", ""))
        right_name = _RIGHT_NAMES.get(detected, "해당 권리")
        marker = _object_marker(right_name)
        point_one = f"고객의 {right_name}{marker} 원칙적으로 보존합니다."
        example_clause = (
            f"고객은 관련 법령과 이 계약에서 정한 절차에 따라 {right_name}{marker} 행사할 수 "
            "있습니다. 권리 행사가 제한되는 경우에는 그 사유·범위·기간을 구체적으로 "
            "명시하고 고객에게 이의제기 및 구제 절차를 안내합니다."
        )
    enriched.update(
        revision_points=[point_one, point_two],
        example_clause=example_clause,
        guidance_version=GUIDANCE_VERSION,
    )
    return enriched
