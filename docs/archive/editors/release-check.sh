#!/bin/bash
# ============================================================
# 轻如烟编辑器·版本发布检查脚本
# 用法: ./release-check.sh [版本号]
#   如果不指定版本号，则检查所有已归档版本
# ============================================================

set -euo pipefail

VERSIONS_ROOT="/vol2/1000/AI专用/编辑器所有版本"
ERRORS=0
WARNINGS=0
PASSES=0

print_header() {
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  $1"
    echo "═══════════════════════════════════════════════════════════"
}

check_file() {
    local path="$1"
    if [[ -f "$path" ]]; then
        echo "  ✓ $path"
        return 0
    else
        echo "  ✗ $path (缺失)"
        ((ERRORS++))
        return 1
    fi
}

check_dir() {
    local path="$1"
    if [[ -d "$path" ]]; then
        echo "  ✓ $path/"
        return 0
    else
        echo "  ✗ $path/ (不存在)"
        ((ERRORS++))
        return 1
    fi
}

check_pycache_in_dir() {
    local dir="$1"
    if find "$dir" -type d -name "__pycache__" | grep -q .; then
        echo "  ⚠ __pycache__ 存在"
        ((WARNINGS++))
        return 1
    fi
    if find "$dir" -name "*.pyc" | grep -q .; then
        echo "  ⚠ .pyc 文件存在"
        ((WARNINGS++))
        return 1
    fi
    return 0
}

check_version() {
    local version="$1"
    local base="$VERSIONS_ROOT/$version"

    if [[ ! -d "$base" ]]; then
        echo "  ✗ 版本目录不存在: $version"
        ((ERRORS++))
        return 1
    fi

    echo ""
    print_header "检查版本: $version ($base)"

    # 核心 Python 文件（所有版本都必须有）
    echo ""
    echo "── 核心 Python 文件 ──"
    for f in server.py handlers/__init__.py utils/__init__.py; do
        check_file "$base/$f"
    done

    # 目录结构（handlers/utils 如果存在则检查）
    echo ""
    echo "── 目录结构 ──"
    for d in handlers utils static templates; do
        if [[ -d "$base/$d" ]]; then
            check_dir "$base/$d"
            # 递归检查 __pycache__
            check_pycache_in_dir "$base/$d"
        else
            echo "  - $d/ (不存在)"
        fi
    done

    # 前端文件（仅 v4+ 需要）
    echo ""
    echo "── 前端文件 ──"
    local has_frontend=0
    if [[ -f "$base/index.html" ]]; then
        check_file "$base/index.html"
        has_frontend=1
    elif [[ -d "$base/static" && -f "$base/static/index.html" ]]; then
        check_file "$base/static/index.html"
        has_frontend=1
    else
        echo "  - index.html (缺失 — 此版本可能为纯后端备份)"
    fi
    if [[ $has_frontend -eq 0 ]]; then
        ((WARNINGS++))
    fi

    # 与 v4 对比（当前运行版本）
    echo ""
    echo "── 与 v4 对比（意外缺失文件）──"
    local v4_base="$VERSIONS_ROOT/v4_20260625_architectural-refactor"
    if [[ -d "$v4_base" ]]; then
        local missing=$(diff <(find "$v4_base" -type f | sort) <(find "$base" -type f | sort) | grep "^<" | cut -d' ' -f2 | head -20)
        if [[ -n "$missing" ]]; then
            echo "  ⚠ v4 有但 $version 缺失的文件:"
            echo "$missing" | while read -r f; do echo "    - $f"; done
            ((WARNINGS++))
        else
            echo "  ✓ 无意外缺失文件"
        fi
    else
        echo "  - v4 基线不存在，跳过对比"
    fi

    echo ""
    if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
        echo "  ✅ 通过"
        ((PASSES++))
        return 0
    else
        echo "  ❌ 未通过 (错误: $ERRORS, 警告: $WARNINGS)"
        return 1
    fi
}

main() {
    local target_version="${1:-all}"

    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║     轻如烟编辑器·版本发布检查                       ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    if [[ "$target_version" == "all" ]]; then
        versions=(
            "v1_20260612_editor-backup"
            "v2_20260613_zuixin"
            "v3_20260622_zuixin2"
            "v4_20260625_architectural-refactor"
            "v4.1_20260626_inject-fix"
        )
    else
        versions=("$target_version")
    fi

    local total_errors=0
    local total_warnings=0
    local total_passes=0

    for ver in "${versions[@]}"; do
        result=$(check_version "$ver") || true
        local errors warnings passes
        errors=$(echo "$result" | grep -oP '\d+' | tail -1)
        warnings=$(echo "$result" | grep -oP '\d+' | tail -2 | head -1)
        passes=$(echo "$result" | grep -c "✅\|✅" || true)
        total_errors=$((total_errors + errors))
        total_warnings=$((total_warnings + warnings))
        total_passes=$((total_passes + passes))
    done

    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  汇总"
    echo "═══════════════════════════════════════════════════════════"
    echo "  总计: $total_passes 通过, $total_errors 错误, $total_warnings 警告"
    echo ""

    if [[ $total_errors -gt 0 ]]; then
        exit 1
    fi

    exit 0
}

main "$@"
