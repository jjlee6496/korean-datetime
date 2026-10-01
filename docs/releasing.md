# 버전과 배포

버전은 Semantic Versioning(`MAJOR.MINOR.PATCH`)을 따릅니다. 공개 API의 호환성이 깨지거나 기존 해석 정책을 의도적으로 바꾸면 MAJOR, 호환되는 기능 추가는 MINOR, 문서화된 동작으로 복구하는 버그 수정은 PATCH를 올립니다.
`pyproject.toml`과 `src/korean_datetime/__init__.py`의 버전을 함께 변경하고 `uv lock`으로 잠금 파일도 맞춥니다. 태그는 `v1.0.0` 형식입니다.

## 첫 배포 연결

PyPI 계정으로 [Pending Publisher 등록](https://pypi.org/manage/account/publishing/)에서 다음을 입력합니다.

| 항목 | 값 |
|---|---|
| PyPI project name | `korean-datetime` |
| GitHub owner | `jjlee6496` |
| Repository | `korean-datetime` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

GitHub 저장소에도 `pypi` environment를 만듭니다. PyPI 이름을 사용할 수 있어야 하며, 등록만으로 패키지가 게시되지는 않습니다. 비밀번호나 장기 API 토큰 없이 GitHub Actions의 OIDC로 게시합니다. [PyPI 공식 안내](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)

## 릴리스 절차

1. 변경 사항을 main에 반영하고 CI 성공을 확인합니다. CI는 Python 3.10~3.13에서 기존 전체 검사와 패키지 빌드·설치 검사를 실행합니다.
2. 버전에 맞는 태그의 GitHub Release를 초안으로 작성합니다. 첫 버전은 `v1.0.0`이며 변경 내용은 README의 1.0.0 변경 사항을 바탕으로 작성합니다.
3. Release를 게시하면 `release.yml`이 태그와 두 버전 값의 일치를 확인하고 CI를 다시 실행합니다. 검증한 바로 그 wheel/sdist를 PyPI에 업로드합니다.
4. 새 환경에서 `pip install korean-datetime==1.0.0`과 CLI를 확인합니다. 성공 후 README 설치 명령을 PyPI 방식으로 변경하고 다음 배지를 추가합니다.

```markdown
[![PyPI](https://img.shields.io/pypi/v/korean-datetime)](https://pypi.org/project/korean-datetime/)
```

PyPI에 올린 버전 파일은 덮어쓸 수 없습니다. 수정 배포는 버전을 올려 새 Release로 진행합니다.
