# 未启用的 GitHub Actions 示例

当前版本不启用 GitHub Actions 或 GitHub Pages。此目录内的 `.yml.example` 是参考文件，不会被 GitHub 自动执行；克隆、安装依赖、本地运行、测试和构建都不依赖 workflow 权限。

- `ci.yml.example`：未来可选的测试与构建流程。
- `pages.yml.example`：未来可选、仅发布虚构数据的静态只读演示流程；不部署私有 API。

本地验证仍使用根目录的 `npm test`、`npm run build` 和 `npm run check:release`。首次运行请按 [项目 README](../../README.md) 安装对应依赖。

若以后决定启用，先单独确认 GitHub 授权、工作流版本与 Pages 设置，再将选定示例复制到 `.github/workflows/` 并去掉 `.example` 后缀；同时在 `.release-files.json` 中登记新增文件、复查公开数据并重新运行发布守卫。仅移动文件并不能完成权限配置。当前没有对 GitHub 账号权限做任何修改。
