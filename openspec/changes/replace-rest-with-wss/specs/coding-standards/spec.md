## ADDED Requirements

### Requirement: 中文 docstring

项目中所有 Python 模块、类、函数的 docstring SHALL 使用简体中文编写。docstring SHALL 遵循 Google Style 格式（`"""简短描述。"""` 或 `"""简短描述。\n\n详细描述。"""`）。

#### Scenario: 新模块的 docstring 为中文
- **WHEN** 新增一个 Python 模块
- **THEN** 模块顶部的 `"""模块功能简述。"""` SHALL 使用中文

#### Scenario: 新函数的 docstring 为中文
- **WHEN** 新增一个函数或方法
- **THEN** 函数体第一行的 docstring SHALL 使用中文描述函数用途

#### Scenario: 类定义的 docstring 为中文
- **WHEN** 新增一个类
- **THEN** 类定义下一行的 docstring SHALL 使用中文描述类的职责

### Requirement: pytest 质量门禁

所有代码变更在合并前 SHALL 通过 `pytest` 全量测试。测试失败 SHALL 阻止合并。CI 流程 SHALL 在 push 或 PR 时自动运行 pytest。

#### Scenario: 提交前本地运行测试
- **WHEN** 开发者完成代码修改，准备提交
- **THEN** 开发者 SHALL 运行 `pytest` 并确认所有测试通过

#### Scenario: 测试失败阻止合并
- **WHEN** pytest 运行结果中存在 FAILED 或 ERROR 状态的测试用例
- **THEN** 代码 SHALL NOT 被合并到主分支

#### Scenario: 新增功能需要对应测试
- **WHEN** 新增或修改业务逻辑
- **THEN** SHALL 同步新增或更新对应的 pytest 测试用例
