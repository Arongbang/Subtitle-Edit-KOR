import re
import sys
import shutil
from pathlib import Path

def remove_little_rest_phrases(line: str) -> str:
    pattern = r'(\s)?少(\s)?し(\s)?休.+[\.。\,\?]{1,}'
    return re.sub(pattern, '', line)

def merge_single_char_captions(srt_content: str) -> str:
    """
    SRT 파일 내용을 읽어와서 '정확히 1글자(공백 제외)'로 된 자막만
    바로 다음 자막과 합쳐주는 핵심 함수

    처리 방식:
    1. SRT를 블록 단위(번호 + 시간 + 텍스트 1~n줄)로 분리
    2. 각 블록의 텍스트에서 모든 공백을 제거한 뒤 길이가 정확히 1인지 확인
    3. 1글자라면 다음 블록의 텍스트를 바로 붙이고, 시간 범위는 첫 시작 ~ 두 번째 끝으로 확장
    4. 번호는 나중에 전체 재번호 매김

    Returns:
        str: 병합이 완료된 새로운 SRT 내용 (문자열)
    """
    # 1. 줄 단위로 나누고 공백 제거
    lines = srt_content.strip().splitlines()

    # 블록 = 하나의 자막 단위 (번호, 시간, 텍스트 여러 줄 가능)
    blocks = []
    current_block = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # 빈 줄 → 이전 블록 종료
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue
        current_block.append(line)  # 원본 줄 그대로 저장 (들여쓰기 유지)

    # 마지막 블록이 남아있으면 추가
    if current_block:
        blocks.append(current_block)

    # 병합된 결과가 들어갈 리스트
    merged = []
    i = 0

    while i < len(blocks):
        block = blocks[i]

        # 비정상 블록(3줄 미만)은 그대로 유지하고 넘김
        if len(block) < 3:
            merged.append(block)
            i += 1
            continue

        # 블록 구조 분해
        num = block[0]          # 자막 번호 (문자열)
        time_line = block[1]    # 시간줄 ex) 00:01:23,450 --> 00:01:24,120
        text_parts = block[2:]  # 텍스트 부분 (1줄 이상 가능)

        #휴식어쩌고 제거
        for j in range(2, len(block)):
            block[j] = remove_little_rest_phrases(block[j])

        # 텍스트 합치고 앞뒤 공백 제거
        text = ' '.join(text_parts).strip()

        # 일본어/중국어 등 띄어쓰기 없는 언어 고려 → 모든 공백 제거 후 길이 체크
        text_clean = re.sub(r'\s+', '', text)           # 스페이스, 탭, 全角공백 등 모두 제거

        # 병합 조건: 현재가 정확히 1글자이고, 다음 블록이 존재할 때
        if i + 1 < len(blocks) and len(text_clean) == 1:
            next_block = blocks[i + 1]

            # 다음 블록도 비정상 → 이번 것도 그대로 두고 넘어감
            if len(next_block) < 3:
                merged.append(block)
                i += 1
                continue

            # 다음 블록 정보 추출
            next_time_line = next_block[1]
            next_text_parts = next_block[2:]
            next_text = ' '.join(next_text_parts).strip()

            # 새 시간 범위: 현재 시작 시각 ~ 다음 자막의 종료 시각
            start_str = time_line.split('-->')[0].strip()
            next_end_str = next_time_line.split('-->')[1].strip()
            new_time_line = f"{start_str} --> {next_end_str}"

            # 텍스트 단순 연결 (일본어는 대부분 띄어쓰기 없이 자연스럽게 붙음)
            combined_text = text + next_text

            # 병합된 블록 생성 (번호는 나중에 다시 붙임)
            merged.append([num, new_time_line, combined_text])

            # 다음 블록까지 처리했으므로 2칸 건너뜀
            i += 2
        else:
            # 병합 조건에 해당하지 않으면 원본 그대로
            merged.append(block)
            i += 1

    # ────────────────────────────────────────────────
    # 최종 SRT 문자열 재구성 (번호 다시 1부터 매김)
    # ────────────────────────────────────────────────
    result_lines = []
    new_index = 1

    for block in merged:
        if len(block) < 3:
            continue

        #if len(block) == 4:
        #    print("block[2] : " + block[2])

        result_lines.append(str(new_index))           # 새 번호
        result_lines.append(block[1])                 # 시간줄 (이미 갱신됨)
        result_lines.append(block[2])                 # 텍스트
        if len(block) > 3:                            # 텍스트가 2줄이상인 경우
            for i in range(3, len(block)):
                result_lines.append(block[i])

        result_lines.append("")                       # 자막 간 빈 줄 (SRT 표준)
        new_index += 1

    # 마지막에 불필요한 개행 없애고, 파일 끝에 개행 하나 추가 (관례)
    return "\n".join(result_lines).rstrip() + "\n"


def process_srt_file(filepath: Path):
    """
    단일 SRT 파일을 처리하는 함수
    1. 백업 파일(.bak) 생성
    2. 내용 읽기 → 병합 → 변경이 있으면 원본 덮어쓰기
    """
    print(f"처리 중: {filepath}")

    # 백업 파일 경로 (같은 폴더에 .srt.bak 로 저장)
    backup_path = filepath.with_suffix(filepath.suffix + '.bak')

    try:
        # ── 1. 백업 생성 ───────────────────────────────────────
        # shutil.copy2 → 메타데이터(생성시간 등)도 함께 복사
        shutil.copy2(filepath, backup_path)
        print(f"  → 백업 생성됨: {backup_path.name}")

        # ── 2. 원본 내용 읽기 ──────────────────────────────────
        # utf-8-sig → Windows 메모장에서 저장한 BOM付き UTF-8도 정상 처리
        original_content = filepath.read_text(encoding="utf-8-sig")

        # ── 3. 병합 수행 ───────────────────────────────────────
        merged_content = merge_single_char_captions(original_content)

        # ── 4. 실제 변경이 있었는지 비교 (공백까지 동일하면 스킵) ──
        if merged_content.strip() != original_content.strip():
            filepath.write_text(merged_content, encoding="utf-8-sig")
            print(f"  → 파일 수정 완료 (원본 덮어쓰기)")
        else:
            print(f"  → 변경 사항 없음")

    except Exception as e:
        print(f"  !!! 오류 발생: {e}")
        if backup_path.exists():
            print(f"  (참고: 백업 파일은 생성되었습니다 - {backup_path.name})")


def main():
    """
    프로그램 진입점
    명령줄 인자로 폴더 경로를 받아 모든 .srt 파일 처리
    """
    # 인자 검사
    if len(sys.argv) != 2:
        print("사용법:")
        print("  python merge_srt.py \"폴더경로\"")
        print("예시:")
        print("  python merge_srt.py \"C:/Users/You/Subtitles\"")
        print("  python merge_srt.py \"./자막\"")
        sys.exit(1)

    # 입력받은 경로 → Path 객체로 변환 & 절대경로로 정규화
    folder_path = Path(sys.argv[1]).resolve()

    # 폴더가 실제로 존재하는지 확인
    if not folder_path.is_dir():
        print(f"오류: {folder_path} 는 존재하지 않거나 폴더가 아닙니다.")
        sys.exit(1)

    # 해당 폴더 안 .srt 파일 모두 찾기 (재귀X, 현재 폴더만)
    srt_files = list(folder_path.rglob("*.srt"))

    if not srt_files:
        print("해당 폴더에 .srt 파일이 하나도 없습니다.")
        return

    print(f"발견된 .srt 파일 수: {len(srt_files)}\n")

    # 파일 하나씩 순차 처리
    for srt_file in srt_files:
        process_srt_file(srt_file)
        print()  # 파일 간 시각적 구분용 빈 줄

    print("===== 모든 파일 처리 완료 =====")


if __name__ == "__main__":
    main()