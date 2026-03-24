tree -I "venv|.venv|__pycache__|build|dist|.git|.idea|.vscode|.pytest_cache|Cache|blob_storage" --prune >code.txt

echo -e "\n\n--- СОДЕРЖИМОЕ ФАЙЛОВ ---\n" >>code.txt

find . \
    -type d \( -name "venv" -o -name ".venv" -o -name "__pycache__" -o -name "build" -o -name "dist" -o -name ".git" -o -name ".vscode" -o -name ".idea" -o -name ".pytest_cache" -o -name "Cache" -o -name "blob_storage" \) -prune \
    -o \
    -type f -not \( \
    -name "*.pyc" -o -name "*.so" -o -name "*.o" -o -name "*.a" \
    -o -name "*.png" -o -name "*.jpg" -o -name "*.jpeg" -o -name "*.gif" -o -name "*.svg" -o -name "*.webp" -o -name "*.ico" \
    -o -name "*.ttf" -o -name "*.otf" -o -name "*.woff" -o -name "*.woff2" -o -name "*.eot" \
    -o -name "*.mp4" -o -name "*.avi" -o -name "*.mkv" -o -name "*.mov" -o -name "*.flv" -o -name "*.webm" -o -name "*.3gp" -o -name "*.mpeg" -o -name "*.mpg" \
    -o -name "*.map" -o -name "*.zip" -o -name "*.gz" -o -name "*.tar" -o -name "*.rar" \
    -o -name "LICENSE" -o -name "LICENSE.txt" \
    \) -print0 | xargs -0 -I {} sh -c 'echo -e "\n\n--- Файл: {} ---"; cat "{}";' >>code.txt

echo "Файл code.txt успешно создан."
