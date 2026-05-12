#!/usr/bin/env python3
"""Generate an iOS Shortcuts .shortcut file that opens whimsical.com on the iPhone home screen."""

import plistlib
from pathlib import Path

SHORTCUT_DATA = {
    "WFWorkflowActions": [
        {
            "WFWorkflowActionIdentifier": "is.workflow.actions.openurl",
            "WFWorkflowActionParameters": {
                "WFURLActionURL": "https://whimsical.com/",
            },
        }
    ],
    "WFWorkflowClientVersion": "1140.0.0",
    "WFWorkflowHasOutputFallback": False,
    "WFWorkflowIcon": {
        "WFWorkflowIconGlyphNumber": 59511,
        "WFWorkflowIconStartColor": 1157895935,
    },
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": [
        "WFAppStoreAppContentItem",
        "WFArticleContentItem",
        "WFContactContentItem",
        "WFDateContentItem",
        "WFEmailAddressContentItem",
        "WFGenericFileContentItem",
        "WFImageContentItem",
        "WFiTunesProductContentItem",
        "WFLocationContentItem",
        "WFDCMapsLinkContentItem",
        "WFAVAssetContentItem",
        "WFPDFContentItem",
        "WFPhoneNumberContentItem",
        "WFRichTextContentItem",
        "WFSafariWebPageContentItem",
        "WFStringContentItem",
        "WFURLContentItem",
    ],
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowName": "Whimsical",
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": [],
}

output_path = Path(__file__).parent / "Whimsical.shortcut"
with open(output_path, "wb") as f:
    plistlib.dump(SHORTCUT_DATA, f, fmt=plistlib.FMT_BINARY)

print(f"생성 완료: {output_path}")
print()
print("아이폰에 설치하는 방법:")
print("1. 이 파일(Whimsical.shortcut)을 아이폰으로 전송 (AirDrop, 이메일 등)")
print("2. 파일을 열면 '단축어' 앱에서 자동으로 열림")
print("3. '단축어 추가'를 탭해 설치")
print("4. 단축어 앱에서 Whimsical 단축어를 길게 누른 뒤 '홈 화면에 추가' 선택")
