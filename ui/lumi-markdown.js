// Lumi's answers in light Markdown: paragraphs, headings, bullet and numbered lists, **bold**, *italic*, `code`
// and fenced code blocks. Everything is built with createElement and textContent, never innerHTML, so text from
// the model (or from a song title or note it quotes) can't become markup, scripts or links. Links are shown as
// their text with the address after it; nothing in an answer can navigate the window.
const LumiMarkdown = (() => {
    const BULLET = /^\s*[-*+•]\s+(.*)$/;
    const NUMBER = /^\s*(\d{1,3})[.)]\s+(.*)$/;
    const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;
    const FENCE = /^\s*```/;
    const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/;

    // Inline marks, longest first: code, bold, italic, links
    const INLINE = /`([^`\n]+)`|\*\*(?=\S)([\s\S]*?\S)\*\*|__(?=\S)([\s\S]*?\S)__|\*(?=[^\s*])([^*\n]*?[^\s*])\*|(?<![\w])_(?=[^\s_])([^_\n]*?[^\s_])_(?![\w])|\[([^\]\n]+)\]\(([^)\s]+)\)/g;

    function inline(parent, text) {
        // matchAll works on its own copy of the pattern, so the nested calls for bold and italic can't reset
        // this loop's position (a shared lastIndex would loop for ever)
        let last = 0;
        for (const m of text.matchAll(INLINE)) {
            if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
            if (m[1] !== undefined) el(parent, 'code', m[1]);
            else if (m[2] !== undefined || m[3] !== undefined) inline(el(parent, 'strong'), m[2] ?? m[3]);
            else if (m[4] !== undefined || m[5] !== undefined) inline(el(parent, 'em'), m[4] ?? m[5]);
            else {
                // A link: its words, then the address in plain text (never clickable inside the island)
                inline(parent, m[6]);
                if (m[7] !== m[6]) el(parent, 'span', ` (${m[7]})`).className = 'md-url';
            }
            last = m.index + m[0].length;
        }
        if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
    }

    function el(parent, tag, text) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        parent.appendChild(node);
        return node;
    }

    // Renders text into target, replacing what was there. Unclosed marks while a reply streams in stay as text.
    function render(target, text) {
        target.replaceChildren();
        target.classList.add('md');
        const lines = String(text ?? '').replace(/\r\n?/g, '\n').split('\n');
        let para = [], list = null, listKind = '';

        const endPara = () => {
            if (!para.length) return;
            const p = el(target, 'p');
            para.forEach((line, i) => { if (i) p.appendChild(document.createElement('br')); inline(p, line); });
            para = [];
        };
        const endList = () => { list = null; listKind = ''; };

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (FENCE.test(line)) {
                endPara(); endList();
                const code = [];
                for (i++; i < lines.length && !FENCE.test(lines[i]); i++) code.push(lines[i]);
                el(el(target, 'pre'), 'code', code.join('\n'));
                continue;
            }
            if (!line.trim()) { endPara(); endList(); continue; }
            let m;
            if ((m = HEADING.exec(line))) {
                endPara(); endList();
                const h = el(target, 'p');
                h.className = 'md-h';
                inline(h, m[1]);
                continue;
            }
            if (RULE.test(line)) { endPara(); endList(); el(target, 'hr'); continue; }
            const bullet = BULLET.exec(line), number = bullet ? null : NUMBER.exec(line);
            if (bullet || number) {
                endPara();
                const kind = bullet ? 'ul' : 'ol';
                if (!list || listKind !== kind) {
                    list = el(target, kind);
                    listKind = kind;
                    if (number && number[1] !== '1') list.start = Number(number[1]);
                }
                inline(el(list, 'li'), bullet ? bullet[1] : number[2]);
                continue;
            }
            if (list && /^\s{2,}\S/.test(line)) {  // an indented line continues the last item
                const item = list.lastChild;
                item.appendChild(document.createTextNode(' '));
                inline(item, line.trim());
                continue;
            }
            endList();
            para.push(line);
        }
        endPara();
        return target;
    }

    return { render };
})();
