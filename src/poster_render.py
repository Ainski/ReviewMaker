"""Pure HTML template: PosterData + hero SVG -> one self-contained HTML string.

CSS is the committed v3 mockup (docs/reference/poster_redesign_mockup.html).
Rendered to PNG by poster_rasterize (headless browser loads the Google Fonts).
"""
import re
from html import escape as _esc

_STYLE = r"""
  :root{
    /* DESIGN.md tokens (GUI system) */
    --primary:#6D5DF6;--primary-hover:#5B4BE0;--primary-light:#F0EEFF;
    --bg:#F6F5F3;--bg-alt:#FAFAF8;--surface:#FFFFFF;--surface-hover:#F7F6F4;
    --border:#E7E3DC;--border-light:#F2EFEA;
    --text:#171717;--text-secondary:#55514A;--text-muted:#96918A;
    --success:#2F9E71;
    --radius:10px;--radius-lg:12px;--radius-xl:14px;
    --shadow-md:0 4px 6px -1px rgb(0 0 0/.07),0 2px 4px -2px rgb(0 0 0/.05);
    --shadow-lg:0 10px 15px -3px rgb(0 0 0/.08),0 4px 6px -4px rgb(0 0 0/.05);
    --font:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
    /* editorial fonts (content treatment) */
    --serif:"Lora","Noto Serif SC",Georgia,serif;
    --mono:"JetBrains Mono",monospace;
    --jost:"Jost","Noto Sans SC",sans-serif;
    --band:#F4F2FC; /* faint purple era tint, GUI-native */
  }
  *{margin:0;padding:0;box-sizing:border-box;}
  body{background:var(--bg);color:var(--text);font-family:var(--font);padding:42px 0;
    background-image:radial-gradient(1200px 460px at 82% -4%,rgba(109,93,246,.06),transparent);}

  /* poster = white surface card sitting inside the GUI */
  .poster{width:1180px;margin:0 auto;background:var(--surface);
    border:1px solid var(--border);border-radius:var(--radius-xl);
    padding:40px 56px 26px;box-shadow:var(--shadow-lg);}

  .rule-full{height:1px;background:var(--border);width:100%;}
  .rule36{width:38px;height:2px;background:var(--primary);margin:13px 0 4px;border-radius:2px;}

  .chrome{display:flex;justify-content:space-between;align-items:center;
    font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;
    text-transform:uppercase;color:var(--text-muted);padding-bottom:9px;}
  .chrome.foot{padding:10px 0 0;margin-top:20px;border-top:1px solid var(--border);}

  .kicker{font-family:var(--mono);font-size:11px;letter-spacing:.2em;
    text-transform:uppercase;color:var(--primary);margin:16px 0 11px;}
  .title{font-family:var(--jost);font-weight:300;font-size:37px;
    line-height:1.2;letter-spacing:-.01em;color:var(--text);}
  .title .zh{font-weight:500;}

  /* stat band */
  .stats{display:flex;gap:0;margin:20px 0 4px;}
  .stat{flex:1;border-top:2px solid var(--text);padding:9px 16px 2px 0;}
  .stat:first-child{border-top-color:var(--primary);}
  .stat .num{font-family:var(--jost);font-weight:200;font-size:46px;line-height:1;
    letter-spacing:-.03em;color:var(--text);}
  .stat .num .u{font-size:23px;}
  .stat .lab{font-family:var(--jost);font-weight:500;font-size:13.5px;color:var(--text);margin-top:8px;}
  .stat .sub{font-family:var(--mono);font-size:8.5px;letter-spacing:.12em;
    text-transform:uppercase;color:var(--text-muted);margin-top:2px;}

  /* hero figure in a GUI card */
  .figwrap{margin-top:20px;border:1px solid var(--border-light);border-radius:var(--radius-lg);
    background:var(--surface);overflow:hidden;padding:6px 6px 0;}
  .figwrap svg{width:100%;height:auto;display:block;}
  .caption{font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;text-transform:uppercase;
    color:var(--text-muted);text-align:center;padding:8px 0 9px;}

  /* serif highlight (pulled from review conclusion) */
  .highlight{font-family:var(--serif);font-weight:400;font-size:22px;line-height:1.5;
    color:var(--text);margin:24px 0 6px;padding-left:18px;border-left:3px solid var(--primary);}
  .lineage{margin-top:22px;}

  /* 图文穿插 bands */
  .band{display:flex;gap:46px;margin-top:24px;align-items:flex-start;}
  .band.alt{border-top:1px solid var(--border);padding-top:22px;}
  .col-text{flex:1.32;}
  .col-viz{flex:1;}
  .sec-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;}
  .sec-h .zh{font-family:var(--jost);font-weight:500;font-size:16px;color:var(--text);}
  .sec-h .en{font-family:var(--mono);font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--text-muted);}

  /* review prose excerpt (the 图文 text — GUI body style, purple left rule) */
  .excerpt{font-family:var(--font);font-size:14px;line-height:1.92;color:var(--text-secondary);
    padding-left:16px;border-left:3px solid var(--primary-light);text-align:justify;}
  .excerpt .em{color:var(--text);font-weight:600;}
  .excerpt + .excerpt{margin-top:13px;}
  .src{font-family:var(--mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--text-muted);margin-top:9px;}

  /* taxonomy bars */
  .bar{margin-bottom:13px;}
  .bar .top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px;}
  .bar .nm{font-family:var(--jost);font-weight:400;font-size:13.5px;color:var(--text);}
  .bar .ct{font-family:var(--jost);font-weight:200;font-size:21px;letter-spacing:-.02em;color:var(--text);}
  .bar .track{height:8px;background:var(--bg-alt);border:1px solid var(--border);border-radius:3px;position:relative;overflow:hidden;}
  .bar .fill{position:absolute;left:0;top:0;bottom:0;background:var(--text);}
  .bar:first-of-type .fill{background:var(--primary);}

  /* trade-off matrix */
  .mtx{width:100%;border-collapse:collapse;}
  .mtx th,.mtx td{border:1px solid var(--border);padding:8px 8px;text-align:center;}
  .mtx th{font-family:var(--mono);font-size:8px;letter-spacing:.08em;text-transform:uppercase;
    color:var(--text-muted);font-weight:400;background:var(--bg-alt);}
  .mtx td.rowh{text-align:left;font-family:var(--jost);font-weight:400;font-size:12px;color:var(--text);white-space:nowrap;}
  .mtx td .mk{font-size:13px;color:var(--primary);line-height:1;}
  .legend{font-family:var(--mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--text-muted);margin-top:9px;}
"""

_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
          '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
          '<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500'
          '&family=Lora:ital,wght@0,400;0,500;1,400&family=JetBrains+Mono:wght@400;500'
          '&family=Noto+Sans+SC:wght@300;400;500;700&family=Noto+Serif+SC:wght@400;600'
          '&display=swap" rel="stylesheet">')

_CJK = re.compile(r"([一-鿿，。：；！？、（）「」]+)")


def _wrap_cjk(text):
    return _CJK.sub(r'<span class="zh">\1</span>', _esc(text))


def _stat(s):
    style = ' style="border-top-color:var(--primary)"' if s.accent else ""
    val = s.value.replace("%", '<span class="u">%</span>')
    return (f'<div class="stat"{style}><div class="num">{val}</div>'
            f'<div class="lab">{_esc(s.label)}</div><div class="sub">{_esc(s.sub)}</div></div>')


def _bar(b):
    extra = ";background:var(--primary)" if b.accent else ""
    return (f'<div class="bar"><div class="top"><span class="nm">{_esc(b.name)}</span>'
            f'<span class="ct">{b.count}</span></div><div class="track">'
            f'<div class="fill" style="width:{b.width_pct}%{extra}"></div></div></div>')


def _excerpt(e):
    return (f'<div class="sec-h"><span class="zh">{_esc(e.heading)}</span>'
            f'<span class="en">{_esc(e.heading_en)}</span></div>'
            f'<div class="excerpt">{_esc(e.text)}</div>'
            f'<div class="src">{_esc(e.source)}</div>')


def _matrix(t):
    head = "".join(f"<th>{_esc(d)}</th>" for d in t.dims)
    body = ""
    for r in t.rows:
        cells = "".join(f'<td><span class="mk">{_esc(m)}</span></td>' for m in r.marks)
        body += f'<tr><td class="rowh">{_esc(r.name)}</td>{cells}</tr>'
    return (f'<table class="mtx"><tr><th>类别 / Lineage</th>{head}</tr>{body}</table>'
            '<div class="legend">● High&nbsp;&nbsp;◐ Medium&nbsp;&nbsp;'
            "— 适用场景由综述横向对比节归纳</div>")


def render_poster_html(data, hero_svg):
    stats = "".join(_stat(s) for s in data.stats)
    bars = "".join(_bar(b) for b in data.taxonomy)
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">{_FONTS}
<style>{_STYLE}</style></head><body><div class="poster">
<div class="chrome"><span>ReviewMaker · 文献综述海报</span><span>AUTO-GENERATED</span></div>
<div class="rule-full"></div>
<div class="kicker">Algorithm Lineage · 算法演进谱系</div>
<div class="title">{_wrap_cjk(data.title)}</div>
<div class="rule36"></div>
<div class="stats">{stats}</div>
<div class="figwrap">{hero_svg}<div class="caption">Fig. 1 — Method Evolution Timeline</div></div>
{('<div class="lineage">' + _excerpt(data.lineage) + '</div>') if getattr(data, "lineage", None) else ''}
<div class="highlight">"{_esc(data.highlight)}"</div>
<div class="band"><div class="col-text">{_excerpt(data.excerpts[0])}</div>
<div class="col-viz"><div class="sec-h"><span class="zh">方法体系分类</span>
<span class="en">Taxonomy</span></div>{bars}</div></div>
<div class="band alt"><div class="col-viz"><div class="sec-h"><span class="zh">横向对比</span>
<span class="en">Trade-offs</span></div>{_matrix(data.tradeoff)}</div>
<div class="col-text">{_excerpt(data.excerpts[1])}</div></div>
<div class="chrome foot"><span>{_esc(data.foot_left)}</span><span>{_esc(data.foot_right)}</span></div>
</div></body></html>"""
