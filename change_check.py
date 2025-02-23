import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import os
import re

def prettify(element):
    """XML 요소를 문자열로 변환하고 들여쓰기를 적용 (줄바꿈 제거 포함)"""
    rough_string = ET.tostring(element, encoding='utf-8').decode('utf-8')  # bytes → str 변환
    rough_string = rough_string.replace("\n", "").strip()  # 줄바꿈 제거 및 공백 정리
    parsed = minidom.parseString(rough_string)  # 문자열 파싱
    return parsed.toprettyxml(indent="  ")

def sanitize_filename(name):
    """파일 이름에 사용할 수 없는 문자 제거 및 공백 처리"""
    # 파일 이름에서 허용되지 않는 문자 제거 (윈도우 기준)
    return re.sub(r'[<>:"/\\|?*]', '', name).replace(" ", "_")

def split_xml_by_group(input_file, output_dir):
    print(f"🔎 입력 파일 경로: {input_file}")
    print(f"📂 출력 폴더 경로: {output_dir}")

    # 출력 디렉토리 생성
    try:
        os.makedirs(output_dir, exist_ok=True)
        print(f"✅ 출력 폴더 확인 및 생성 완료")
    except Exception as e:
        print(f"❌ 출력 폴더 생성 중 오류 발생: {e}")
        return

    # XML 파싱
    try:
        print("📥 XML 파일 파싱 시작...")
        tree = ET.parse(input_file)
        root = tree.getroot()
        print("✅ XML 파싱 성공!")
    except Exception as e:
        print(f"❌ XML 파싱 중 오류 발생: {e}")
        return

    # Group 태그 찾기
    parent = root.find('MultipleSearchAndReplaceList')
    if parent is None:
        print("⚠️ <MultipleSearchAndReplaceList> 태그가 발견되지 않았습니다.")
        return

    groups = parent.findall('Group')
    print(f"🔎 발견된 <Group> 태그 개수: {len(groups)}")

    if not groups:
        print("⚠️ <Group> 태그가 발견되지 않았습니다.")
        return

    # Group 태그마다 파일 생성
    for idx, group in enumerate(groups, start=1):
        # <Name> 태그 값 가져오기
        name_tag = group.find('Name')
        if name_tag is not None and name_tag.text:
            filename = sanitize_filename(name_tag.text)
        else:
            filename = f"group_{idx}"

        output_file = os.path.join(output_dir, f"{filename}.xml")

        try:
            # 새로운 루트 요소와 구조 생성
            new_root = ET.Element('Settings')
            new_parent = ET.SubElement(new_root, 'MultipleSearchAndReplaceList')
            new_parent.append(group)

            # 들여쓰기 적용된 XML 문자열 생성
            pretty_xml = prettify(new_root)

            # 파일로 저장
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(pretty_xml)
            print(f"✅ 파일 생성 완료: {output_file}")
        except Exception as e:
            print(f"❌ 파일 생성 중 오류 발생 ({output_file}): {e}")

# 사용 예시 (원시 문자열 사용)
input_xml = r".\multiple_replace_groups.template"
output_directory = r".\change_check"
split_xml_by_group(input_xml, output_directory)
