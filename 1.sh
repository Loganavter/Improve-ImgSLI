#!/bin/bash

OUTPUT_FILE="code.txt"
THRESHOLD=8000 # Порог строк, после которого папка раскрывается

IGNORE_DIRS_FIND="-name venv -o -name .venv -o -name tests -o -name .claude -o -name __pycache__ -o -name build -o -name dist -o -name .git -o -name .vscode -o -name .idea -o -name .pytest_cache -o -name Cache -o -name blob_storage -o -name packages -o -name .agents -o -name .codex -o -name .github"
EXCLUDE_DIRS_REGEX="/(venv|\.venv|__pycache__|build|dist|\.git|\.idea|\.vscode|\.pytest_cache|Cache|blob_storage|\.agents|\.codex|\.claude|\.github|packages)(/|$)"
IGNORE_FILES_FIND="-name $OUTPUT_FILE -name 1.sh -name cleanup_project.py -o -name *.pyc -o -name *.so -o -name *.o -o -name *.a -o -name *.png -o -name *.jpg -o -name *.jpeg -o -name *.gif -o -name *.svg -o -name *.webp -o -name *.ico -o -name *.ttf -o -name *.otf -o -name *.woff -o -name *.woff2 -o -name *.eot -o -name *.mp4 -o -name *.avi -o -name *.mkv -o -name *.mov -o -name *.flv -o -name *.webm -o -name *.3gp -o -name *.mpeg -o -name *.mpg -o -name *.map -o -name *.zip -o -name *.gz -o -name *.tar -o -name *.rar -o -name LICENSE -o -name LICENSE.txt"

TREE_IGNORE_PATTERN="venv|.venv|tests|.claude|__pycache__|build|dist|.git|.vscode|.idea|.pytest_cache|Cache|blob_storage|packages|.agents|.codex|.github"
TREE_IGNORE_PATTERN+="|$OUTPUT_FILE|1.sh|cleanup_project.py|LICENSE|LICENSE.txt"
TREE_IGNORE_PATTERN+="|*.pyc|*.so|*.o|*.a|*.png|*.jpg|*.jpeg|*.gif|*.svg|*.webp|*.ico|*.ttf|*.otf|*.woff|*.woff2|*.eot"
TREE_IGNORE_PATTERN+="|*.mp4|*.avi|*.mkv|*.mov|*.flv|*.webm|*.3gp|*.mpeg|*.mpg|*.map|*.zip|*.gz|*.tar|*.rar"

get_stats() {
    local target="$1"
    local is_pkg="$2"

    local current_ignore="$IGNORE_DIRS_FIND"
    if [ "$is_pkg" = "true" ]; then
        current_ignore="-name venv -o -name .venv -o -name .git"
    fi

    local files_to_ignore_find="$IGNORE_FILES_FIND -o -name .codex -o -name .agents"

    local res=$(find "$target" \
        -type d \( $current_ignore \) -prune \
        -o \
        -type f -not \( $files_to_ignore_find \) -print0 | xargs -0 wc -l -m 2>/dev/null | tail -n 1)

    local lines=$(echo $res | awk '{print $1}')
    local chars=$(echo $res | awk '{print $2}')
    echo "${lines:-0} ${chars:-0}"
}

print_dir_stats() {
    local dir="$1"
    local indent="$2"

    if [[ "$dir" != "." && "$dir" =~ $EXCLUDE_DIRS_REGEX ]]; then return; fi

    read d_lines d_chars <<<$(get_stats "$dir" "false")

    if [[ "$d_lines" != "0" ]]; then
        local prefix=""
        if [ "$indent" -gt 0 ]; then
            prefix="$(printf ' %.0s' $(seq 1 $((indent * 2))))-> "
        fi

        printf "%-55s | %-10s | %-10s\n" "${prefix}${dir}" "$d_lines" "$d_chars" >>"$OUTPUT_FILE"

        if [ "$d_lines" -gt $THRESHOLD ]; then
            while IFS= read -r subdir; do
                print_dir_stats "$subdir" $((indent + 1))
            done < <(find "$dir" -maxdepth 1 -mindepth 1 -type d | sort)
        fi
    fi
}

tree -I "$TREE_IGNORE_PATTERN" --prune >"$OUTPUT_FILE"

if [ -d "packages" ]; then
    echo -e "\n\n--- ДЕРЕВО ПАПКИ packages ---\n" >>"$OUTPUT_FILE"
    tree packages -I "*.pyc|__pycache__" >>"$OUTPUT_FILE"

    echo -e "\n\n--- СОДЕРЖИМОЕ MD-ФАЙЛОВ ИЗ packages ---\n" >>"$OUTPUT_FILE"

    while IFS= read -r -d '' md_file; do
        if [ -s "$md_file" ]; then
            echo -e "\n\n--- Файл: $md_file ---" >>"$OUTPUT_FILE"
            cat "$md_file" >>"$OUTPUT_FILE"
        fi
    done < <(find packages -type f -name "*.md" -print0)
fi

echo -e "\n\n--- СОДЕРЖИМОЕ ФАЙЛОВ ОСНОВНОГО ПРОЕКТА ---\n" >>"$OUTPUT_FILE"

total_lines=0
total_chars=0

files_to_ignore_find_full="$IGNORE_FILES_FIND -o -name .codex -o -name .agents"

while IFS= read -r -d '' file; do
    current_lines=$(wc -l <"$file")
    current_chars=$(wc -m <"$file")
    total_lines=$((total_lines + current_lines))
    total_chars=$((total_chars + current_chars))
    echo -e "\n\n--- Файл: $file (Строк: $current_lines) ---" >>"$OUTPUT_FILE"
    cat "$file" >>"$OUTPUT_FILE"
done < <(find . -type d \( $IGNORE_DIRS_FIND \) -prune -o -type f -not \( $files_to_ignore_find_full \) -print0)

echo -e "\n\n========================================" >>"$OUTPUT_FILE"
echo "СТАТИСТИКА ПО ПАПКАМ (порог раскрытия: $THRESHOLD строк):" >>"$OUTPUT_FILE"
printf "%-55s | %-10s | %-10s\n" "Директория" "Строк" "Символов" >>"$OUTPUT_FILE"
echo "------------------------------------------------------------------------" >>"$OUTPUT_FILE"

while IFS= read -r top_dir; do
    print_dir_stats "$top_dir" 0
done < <(find . -maxdepth 1 -mindepth 1 -type d | sort)

pkg_lines=0
pkg_chars=0
if [ -d "packages" ]; then
    read pkg_lines pkg_chars <<<$(get_stats "packages" "true")
    echo "------------------------------------------------------------------------" >>"$OUTPUT_FILE"
    printf "%-55s | %-10s | %-10s\n" "PACKAGES (внешние библиотеки)" "$pkg_lines" "$pkg_chars" >>"$OUTPUT_FILE"
fi

echo "------------------------------------------------------------------------" >>"$OUTPUT_FILE"
echo "ИТОГОВАЯ СТАТИСТИКА:" >>"$OUTPUT_FILE"
echo "Весь основной код:       $total_lines строк" >>"$OUTPUT_FILE"
echo "Папка packages:          $pkg_lines строк" >>"$OUTPUT_FILE"
echo "----------------------------------------" >>"$OUTPUT_FILE"
echo "ОБЩЕЕ (код + packages):  $((total_lines + pkg_lines)) строк" >>"$OUTPUT_FILE"
echo "========================================" >>"$OUTPUT_FILE"

echo "Готово! Результат в $OUTPUT_FILE (Порог: $THRESHOLD)"
