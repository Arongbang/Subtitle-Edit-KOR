import re
import sys
import shutil
from pathlib import Path
import deepl
from dotenv import load_dotenv
import os

# .env 파일 로드 (프로젝트 루트에 .env 파일 필요)
load_dotenv()

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
if not DEEPL_API_KEY:
    print("오류: .env 파일에 DEEPL_API_KEY가 설정되어 있지 않습니다.")
    print("예시 .env 내용:")
    print('DEEPL_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx:fx')
    sys.exit(1)

# DeepL 클라이언트 초기화 (무료 계정이면 server_url 지정 가능)
try:
    translator = deepl.Translator(DEEPL_API_KEY)
    # 무료 계정인 경우 아래 주석 해제
    translator = deepl.Translator(DEEPL_API_KEY, server_url="https://api-free.deepl.com")
except Exception as e:
    print(f"DeepL 초기화 실패: {e}")
    sys.exit(1)


def translate_ja_to_ko(text: str) -> str:
    """
    일본어 → 한국어 번역 (야동/AV 자막 스타일에 최적화)
    """
    if not text.strip():
        return text

    try:
        result = translator.translate_text(
            text,
            source_lang="JA",
            target_lang="KO",
            formality="prefer_less",               # 반말·캐주얼·직설적 최대한 유도
            model_type="quality_optimized",        # 최고 품질 모델 사용
            context=(
                "일본 AV 자막 번역입니다. "
                "기본적으로 캐주얼한 반말을 사용하지만, 존댓말을 사용할 때는 -요 체의 부드러운 존댓말을 자연스럽게 섞어주세요. "
                "♡ 같은 이모티콘을 분위기에 맞춰 적절히 추가하여 분위기를 살려주세요."
            ),
            preserve_formatting=True,              # !? … ♡ 같은 기호 유지
            split_sentences="1",                   # 문장 단위 적당히 분할
        )
        return result.text.strip()
    except deepl.DeepLException as e:
        print(f"번역 오류: {e}")
        return f"[번역 실패] {text}"


def get_srt_files(folder_path: Path) -> list[Path]:
    return [
        p for p in folder_path.rglob("*.srt")
        if p.suffix == ".srt" and not p.stem.endswith(".ko")
    ]


def remove_little_rest_phrases(line: str) -> str:
    pattern = r'(\s)?少(\s)?し(\s)?休[^\.。\,\?]{1,}[\.。\,\?]{1,}'
    return re.sub(pattern, '', line)


def merge_single_char_captions(srt_content: str) -> str:
    # (기존 함수 내용 그대로 유지 - 생략해서 코드 길이 줄임)
    lines = srt_content.strip().splitlines()
    blocks = []
    current_block = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
        current_block.append(line)

    if current_block:
        blocks.append(current_block)

    merged = []
    i = 0

    while i < len(blocks):
        block = blocks[i]
        if len(block) < 3:
            merged.append(block)
            i += 1
            continue

        num = block[0]
        time_line = block[1]
        text_parts = block[2:]

        for j in range(2, len(block)):
            block[j] = remove_little_rest_phrases(block[j])

        text = ' '.join(text_parts).strip()
        text_clean = re.sub(r'\s+', '', text)

        if i + 1 < len(blocks) and len(text_clean) == 1:
            next_block = blocks[i + 1]
            if len(next_block) < 3:
                merged.append(block)
                i += 1
                continue

            next_time_line = next_block[1]
            next_text_parts = next_block[2:]
            next_text = ' '.join(next_text_parts).strip()

            start_str = time_line.split('-->')[0].strip()
            next_end_str = next_time_line.split('-->')[1].strip()
            new_time_line = f"{start_str} --> {next_end_str}"

            combined_text = text + next_text

            merged.append([num, new_time_line, combined_text])
            i += 2
        else:
            merged.append(block)
            i += 1

    # 재구성
    result_lines = []
    new_index = 1

    for block in merged:
        if len(block) < 3:
            continue

        result_lines.append(str(new_index))
        result_lines.append(block[1])
        result_lines.append(block[2])  # 이미 병합된 텍스트 (또는 원본)

        # 원본이 여러 줄 텍스트였다면 (드물지만)
        if len(block) > 3:
            for extra in block[3:]:
                result_lines.append(extra)

        result_lines.append("")
        new_index += 1

    return "\n".join(result_lines).rstrip() + "\n"


def process_srt_file(filepath: Path):
    print(f"처리 중: {filepath}")

    backup_path = filepath.with_suffix(filepath.suffix + '.bak')
    output_path = filepath.with_stem(filepath.stem + ".ko").with_suffix(".srt")

    if output_path.exists():
        print(f"  → 이미 {output_path.name} 파일이 존재합니다. 스킵.")
        return

    try:
        # 백업 (원본 보호)
        shutil.copy2(filepath, backup_path)
        print(f"  → 백업 생성: {backup_path.name}")

        # 원본 읽기
        original_content = filepath.read_text(encoding="utf-8-sig")

        # 1. 1글자 자막 병합
        merged_content = merge_single_char_captions(original_content)
        if merged_content.strip() != original_content.strip():
            filepath.write_text(merged_content, encoding="utf-8-sig")
            print(f"  → 1글자 병합 수정 완료 (원본 덮어쓰기)")
        else:
            print(f"  → 1글자 병합 변경 사항 없음")

        # 2. 번역 수행 (블록 단위로 번역 → 자막 스타일 유지)
        lines = merged_content.splitlines()
        translated_lines = []
        in_text_block = False
        current_text = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                # 빈 줄 → 텍스트 블록 종료 → 번역 실행
                if current_text:
                    text_to_translate = "\n".join(current_text)
                    translated = translate_ja_to_ko(text_to_translate)
                    translated_lines.extend(translated.splitlines())
                    current_text = []
                translated_lines.append("")  # 빈 줄 유지
                in_text_block = False
                continue

            if re.match(r'^\d+$', stripped):  # 번호 줄
                if current_text:
                    # 이전 텍스트 블록 번역
                    text_to_translate = "\n".join(current_text)
                    translated = translate_ja_to_ko(text_to_translate)
                    translated_lines.extend(translated.splitlines())
                    current_text = []
                translated_lines.append(line)
                in_text_block = False
                continue

            if "-->" in stripped:  # 시간 줄
                translated_lines.append(line)
                in_text_block = True
                continue

            # 텍스트 줄
            if in_text_block:
                current_text.append(line)
            else:
                translated_lines.append(line)

        # 마지막 블록 처리
        if current_text:
            text_to_translate = "\n".join(current_text)
            translated = translate_ja_to_ko(text_to_translate)
            translated_lines.extend(translated.splitlines())

        translated_content = "\n".join(translated_lines).rstrip() + "\n"

        # 결과 저장 (.ko.srt)
        output_path.write_text(translated_content, encoding="utf-8-sig")
        print(f"  → 한국어 자막 저장 완료: {output_path.name}")

    except Exception as e:
        print(f"  !!! 오류: {e}")
        if backup_path.exists():
            print(f"  (백업은 생성됨: {backup_path.name})")


def main():
    if len(sys.argv) != 2:
        print("사용법: python merge_and_translate_srt.py \"폴더경로\"")
        sys.exit(1)

    folder_path = Path(sys.argv[1]).resolve()

    if not folder_path.is_dir():
        print(f"오류: {folder_path} 는 폴더가 아닙니다.")
        sys.exit(1)

    srt_files = get_srt_files(folder_path)

    if not srt_files:
        print("해당 폴더에 처리할 .srt 파일이 없습니다.")
        return

    print(f"발견된 .srt 파일 수: {len(srt_files)}\n")

    for srt_file in srt_files:
        process_srt_file(srt_file)
        print()

    print("===== 모든 파일 처리 완료 =====")


if __name__ == "__main__":
    main()