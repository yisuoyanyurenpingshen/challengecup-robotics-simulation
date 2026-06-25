1. 回到服务器主目录
由于原来的 wangxin 文件夹已经删除，终端曾经停留在一个不存在的旧目录里，导致出现：
fatal: 不能获取当前工作目录：没有那个文件或目录
因此先回到真实存在的目录：
cd /home/bktx
pwd
确认当前位置为：
/home/bktx
2. 新建 projects 目录
为了不再依赖已经删除的 wangxin 目录，重新建立统一项目目录：
mkdir -p /home/bktx/projects
cd /home/bktx/projects
3. 新建挑战杯项目文件夹
mkdir challengecup-robotics-simulation
cd challengecup-robotics-simulation
此时项目路径为：
/home/bktx/projects/challengecup-robotics-simulation
4. 初始化 Git 仓库
执行：
git init
这一步是整个项目“拥有 Git”的关键步骤。
git init 会在当前目录生成隐藏文件夹：
.git/
从这一刻开始，当前目录就成为了 Git 仓库。
5. 设置 main 分支
一开始执行：
git branch -M main
曾经报错：
refs/heads/master not found
原因是刚初始化的 Git 仓库还没有任何 commit，因此还没有真正生成分支。
后来使用：
git symbolic-ref HEAD refs/heads/main
将当前仓库的默认分支指向 main。
再执行：
git status
显示：
On branch main
No commits yet
说明分支设置成功。
6. 连接 GitHub 远程仓库
执行：
git remote add origin https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation.git
这一步把本地 Git 仓库和 GitHub 仓库连接起来。
检查远程仓库：
git remote -v
可以看到：
origin  https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation.git (fetch)
origin  https://github.com/yisuoyanyurenpingshen/challengecup-robotics-simulation.git (push)
四、当前项目目录结构
当前项目结构为：
challengecup-robotics-simulation/
├── README.md
├── .gitignore
├── docs/
│   └── README.md
├── logs/
│   └── README.md
├── scripts/
│   └── README.md
├── configs/
│   └── README.md
├── results/
│   └── README.md
├── datasets/
│   └── README.md
├── weights/
│   └── README.md
└── envs/
    └── README.md
五、各目录作用
目录	作用
docs/	技术笔记、方案分析、学习总结
logs/	每日工程日志
scripts/	实验脚本、测试脚本、工具脚本
configs/	环境配置、实验配置说明
results/	轻量级实验结果、表格、截图说明
datasets/	数据集说明，不存放大型原始数据集
weights/	模型权重说明，不存放大型权重文件
envs/	环境说明，不存放完整虚拟环境
六、为什么每个文件夹都要有 README.md

Git 默认不会记录空文件夹。
所以如果一个目录是空的，即使它在 VS Code 中存在，GitHub 上也不会显示。
因此给每个目录放一个 README.md，作用是：
让 Git 能记录这个目录。
让 GitHub 能显示这个目录。
说明这个目录应该放什么、不应该放什么。
七、.gitignore 的作用

.gitignore 用于告诉 Git 哪些文件不要记录、不要上传。

本项目中 .gitignore 主要用于排除：

Python 缓存
虚拟环境
Conda 环境
大型数据集
大型模型权重
训练输出目录
视频文件
压缩包
SSH 密钥
Token
服务器私有配置

这样可以避免把大文件、敏感文件或无意义文件上传到 GitHub。

八、当前 Git 状态说明

VS Code 左侧文件旁边出现的 U 表示：

Untracked

意思是这些文件已经存在，但还没有被 Git 正式记录。

后续执行：

git add .
git commit -m "init: 重建挑战杯项目结构"

之后，这些文件才会成为 Git 历史的一部分。

九、后续标准 Git 工作流
查看当前状态
git status
添加修改
git add .
保存一次版本
git commit -m "本次修改说明"
上传到 GitHub
git push
查看历史版本
git log --oneline
恢复未提交的错误修改
git restore .
撤销某一次已提交修改
git revert <commit_id>
十、当前阶段结论

本次已经完成：

从 /home/bktx 重新建立项目目录。
创建 /home/bktx/projects/challengecup-robotics-simulation。
使用 git init 初始化 Git 仓库。
将默认分支设置为 main。
连接 GitHub 远程仓库。
创建标准项目目录结构。
创建根目录中文 README.md。
创建 .gitignore。
为各子目录补充中文 README.md。
明确本项目不再使用 wangxin/ 作为仓库根目录。

当前项目已经具备长期 Git 版本管理基础。

下一步是执行：

git status
git add .
git commit -m "init: 重建挑战杯项目结构"

然后根据情况推送到 GitHub。
EOF


---

## 检查是否写入成功

执行：

```bash
ls docs

你应该看到：

01_git_project_setup_summary.md
README.md

再执行：

head docs/01_git_project_setup_summary.md

应该能看到：

# 服务器端 Git 项目搭建总结