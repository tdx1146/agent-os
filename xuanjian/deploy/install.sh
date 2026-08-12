#!/usr/bin/env bash
# IsoSand — 一键部署/设置脚本
# Usage: bash deploy/install.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$PROJECT_DIR/src"
DATA_DIR="$PROJECT_DIR/data"
ESSENCE_DIR="$DATA_DIR/essence"
FACTS_FILE="$DATA_DIR/facts.dict.md"

echo "========================================"
echo "  IsoSand v0.2 — 安装/设置"
echo "========================================"

# ─── 1. 检查 Python 版本 ──────────────────────
echo ""
echo "[1/5] 检查 Python 版本……"
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python >= 3.10"
    exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "❌ Python 版本 $PY_VER < 3.10，请升级"
    exit 1
fi
echo "✅ Python $PY_VER"

# ─── 2. 创建必要目录 ──────────────────────
echo ""
echo "[2/5] 创建必要目录……"
mkdir -p "$ESSENCE_DIR"
echo "✅ $ESSENCE_DIR"

# ─── 3. 初始化 facts.dict.md ──────────────────────
echo ""
echo "[3/5] 检查 facts.dict.md……"
if [ ! -f "$FACTS_FILE" ]; then
    cat > "$FACTS_FILE" << 'FACTS_EOF'
# IsoSand Facts Dictionary
> 断言图 — "关系先于实体"
> 每行一个原子断言，git 可追溯
>
> 格式说明：
> ## ├ <namespace>:<topic>
> - [YYYY-MM-DD] <断言文本>

<!-- 初始版本，尚无断言 -->
FACTS_EOF
    echo "✅ 已创建 $FACTS_FILE"
else
    echo "✅ $FACTS_FILE 已存在（$(( $(wc -l < "$FACTS_FILE") )) 行）"
fi

# ─── 4. 验证 src/ 模块 ──────────────────────
echo ""
echo "[4/5] 验证 src/ 模块……"
MODULES=(iso_logger facts_manager essence_distiller)
MISSING=()
cd "$PROJECT_DIR"
for mod in "${MODULES[@]}"; do
    MOD_FILE="$SRC_DIR/${mod}.py"
    if [ -f "$MOD_FILE" ]; then
        if python3 -c "import sys; sys.path.insert(0, '$SRC_DIR'); import $mod; print(f'✅ {mod}.py — OK')" 2>/dev/null; then
            :
        else
            echo "⚠️  $mod.py 存在但 import 失败（可能缺少依赖）"
        fi
    else
        MISSING+=("$mod")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "⚠️  以下模块尚未创建：${MISSING[*]}"
    echo "   （v0.2 架构规划中，可后续添加）"
fi

# ─── 5. 摘要输出 ──────────────────────
echo ""
echo "========================================"
echo "  IsoSand 安装摘要"
echo "========================================"
echo "  项目路径 : $PROJECT_DIR"
echo "  Python    : $PY_VER ($(which python3))"
echo "  src/ 模块 : $(ls "$SRC_DIR"/*.py 2>/dev/null | wc -l) 文件"
echo "  data/     : $(ls -A "$DATA_DIR" 2>/dev/null | wc -l) 项目"
echo "  essence/  : $(ls "$ESSENCE_DIR" 2>/dev/null | wc -l) 文件"
echo "  facts     : $(wc -l < "$FACTS_FILE") 行"
echo "========================================"
echo "✅ IsoSand 环境就绪"
