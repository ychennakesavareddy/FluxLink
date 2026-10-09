def make_code(lines: int, kind: str) -> str:
    # Deterministically generates realistic Python source
    # kinds: ascii, unicode, crlf, mixed_endings
    result = []
    nl = "\r\n" if kind == "crlf" else "\n"
    for i in range(lines):
        if kind == "mixed_endings":
            nl = "\r\n" if i % 2 == 0 else "\n"
            
        if i % 10 == 0:
            result.append(f"def func_{i}():" + nl)
        elif i % 10 == 1:
            if kind == "unicode":
                result.append(f"    # తెలుగు 🚀 test japanese: コンピュータ" + nl)
            else:
                result.append(f"    # Comment line {i}" + nl)
        elif i % 10 == 5:
            result.append("" + nl) # blank line
        else:
            result.append(f"    print('Line {i} content. 0123456789' * 2)" + nl)
            
    # Trailing newline is included above
    return "".join(result)

if __name__ == "__main__":
    content = make_code(2000, "unicode")
    import os
    parent = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    with open(os.path.join(parent, "2000_lines.py"), "w", encoding="utf-8") as f:
        f.write(content)
