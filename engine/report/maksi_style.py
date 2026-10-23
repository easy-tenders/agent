#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Рендерер отчётов в стиле Макси. Палитра и шрифты — video-pipeline/config.py.

Шрифты лежат в репозитории (`fonts/`, лицензия SIL OFL — распространять
разрешено), поэтому отчёт собирается одинаково на любой машине. Системные
шрифты берутся только как запасной вариант.
"""
import os
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
                                Table, TableStyle)

FONTS = [("Inter", "Inter-Regular"), ("Inter-SB", "Inter-SemiBold"),
         ("Inter-XB", "Inter-ExtraBold"), ("PF", "PlayfairDisplay-SemiBold"),
         ("PF-It", "PlayfairDisplay-SemiBoldItalic")]

# Порядок поиска: сначала репозиторий, потом системные папки шрифтов.
FONT_DIRS = [Path(__file__).resolve().parent / "fonts",
             Path.home() / "Library" / "Fonts",                      # macOS
             Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",  # Windows
             Path.home() / ".local" / "share" / "fonts"]              # Linux


def _register_fonts():
    missing = []
    for name, file in FONTS:
        for d in FONT_DIRS:
            p = d / f"{file}.ttf"
            if p.exists():
                pdfmetrics.registerFont(TTFont(name, str(p)))
                break
        else:
            missing.append(f"{file}.ttf")
    if missing:
        # Встроенные шрифты reportlab кириллицу не отображают — молча
        # подменять нельзя, отчёт вышел бы пустыми строками.
        raise RuntimeError(
            "не найдены шрифты: " + ", ".join(missing) +
            "\nОни должны лежать в engine/report/fonts/ (входят в репозиторий). "
            "Если папка пуста — восстанови её: git checkout engine/report/fonts")


_register_fonts()

NAVY=colors.HexColor("#0a1929"); ACCENT=colors.HexColor("#5f9bff"); ACC2=colors.HexColor("#74a6ff")
INK=colors.HexColor("#12202e"); MUTED=colors.HexColor("#6b7a8c"); LINE=colors.HexColor("#dde3ea")
ZEBRA=colors.HexColor("#f5f7fa"); LOSS=colors.HexColor("#b2472f"); GOOD=colors.HexColor("#1f7a5a")
W,H=A4; ML,MR,MT,MB=20*mm,20*mm,24*mm,20*mm

def _st(n,**kw):
    b=dict(fontName="Inter",fontSize=9.6,leading=14.4,textColor=INK,spaceAfter=0); b.update(kw)
    return ParagraphStyle(n,**b)

S={"h1":_st("h1",fontName="PF",fontSize=21,leading=25,textColor=NAVY,spaceAfter=3*mm),
   "h2":_st("h2",fontName="Inter-XB",fontSize=12.5,leading=16,textColor=NAVY,spaceBefore=6*mm,spaceAfter=2.5*mm),
   "h3":_st("h3",fontName="Inter-SB",fontSize=10.4,leading=14,textColor=NAVY,spaceBefore=4*mm,spaceAfter=1.6*mm),
   "kick":_st("kick",fontName="Inter-SB",fontSize=7.6,leading=10,textColor=ACCENT),
   "body":_st("body",spaceAfter=2.2*mm),
   "lead":_st("lead",fontSize=11,leading=16.5,spaceAfter=3*mm),
   "small":_st("small",fontSize=8.4,leading=12.4,textColor=MUTED,spaceAfter=1.6*mm),
   "cellL":_st("cellL",fontSize=8.5,leading=11.2),
   "cellR":_st("cellR",fontSize=8.5,leading=11.2,alignment=TA_RIGHT),
   "cellG":_st("cellG",fontSize=8.5,leading=11.2,alignment=TA_RIGHT,textColor=GOOD,fontName="Inter-SB"),
   "cellW":_st("cellW",fontSize=8.5,leading=11.2,textColor=LOSS),
   "cellLoss":_st("cellLoss",fontSize=8.5,leading=11.2,alignment=TA_RIGHT,textColor=LOSS),
   "cellH":_st("cellH",fontName="Inter-SB",fontSize=7.8,leading=10.4,textColor=colors.white),
   "cellHR":_st("cellHR",fontName="Inter-SB",fontSize=7.8,leading=10.4,textColor=colors.white,alignment=TA_RIGHT),
   "white":_st("white",fontSize=9.6,leading=14,textColor=colors.white),
   "wsoft":_st("wsoft",fontSize=9.4,leading=14,textColor=colors.HexColor("#d9e2ec"))}

def kicker(c,x,y,t,size=7.6,color=ACCENT,track=0.22):
    c.saveState(); c.setFont("Inter-SB",size); c.setFillColor(color); cx=x; tr=size*track
    for ch in t.upper():
        c.drawString(cx,y,ch); cx+=c.stringWidth(ch,"Inter-SB",size)+tr
    c.restoreState()

def P(t,s="body"): return Paragraph(t,S[s])
def money(v): return f"{v:,.0f}".replace(",", " ")
def trim(s,n):
    s=" ".join(str(s).split())
    return s if len(s)<=n else s[:n].rsplit(" ",1)[0].rstrip(" ,·")+"…"

def table(head,rows,widths,aligns=None,highlight=None,cols=None):
    aligns=aligns or ["L"]+["R"]*(len(head)-1)
    data=[[Paragraph(h,S["cellH" if a=="L" else "cellHR"]) for h,a in zip(head,aligns)]]
    for r in rows:
        cells=[]
        for i,(v,a) in enumerate(zip(r,aligns)):
            key=(cols or {}).get(i) or ("cellL" if a=="L" else "cellR")
            cells.append(Paragraph(str(v),S[key]))
        data.append(cells)
    t=Table(data,colWidths=widths,repeatRows=1)
    stl=[("BACKGROUND",(0,0),(-1,0),NAVY),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
         ("TOPPADDING",(0,0),(-1,-1),3.6),("BOTTOMPADDING",(0,0),(-1,-1),3.6),
         ("LEFTPADDING",(0,0),(-1,-1),5),("RIGHTPADDING",(0,0),(-1,-1),5),
         ("LINEBELOW",(0,1),(-1,-1),0.4,LINE)]
    for i in range(1,len(data)):
        if i%2==0: stl.append(("BACKGROUND",(0,i),(-1,i),ZEBRA))
    for i in (highlight or []): stl.append(("BACKGROUND",(0,i),(-1,i),colors.HexColor("#eaf1ff")))
    t.setStyle(TableStyle(stl)); return t

def panel(lines,accent_first=False):
    inner=[Paragraph(l,S["white"] if (accent_first and i==0) else S["wsoft"]) for i,l in enumerate(lines)]
    t=Table([[inner]],colWidths=[W-ML-MR])
    t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),
        ("LEFTPADDING",(0,0),(-1,-1),9*mm),("RIGHTPADDING",(0,0),(-1,-1),9*mm),
        ("TOPPADDING",(0,0),(-1,-1),6*mm),("BOTTOMPADDING",(0,0),(-1,-1),6*mm),
        ("LINEABOVE",(0,0),(-1,0),1.6,ACCENT)])); return t

def make_cover(kicker_text, title1, title2, lines, figures, footer_left, for_whom=""):
    def cover(c,doc):
        c.saveState(); c.setFillColor(NAVY); c.rect(0,0,W,H,fill=1,stroke=0)
        c.setFillColor(colors.white); c.setFillAlpha(0.16); c.rect(0,H-2,W,2,fill=1,stroke=0); c.setFillAlpha(1)
        kicker(c,ML,H-46*mm,kicker_text,9)
        c.setFont("PF",33); c.setFillColor(colors.white); c.drawString(ML,H-62*mm,title1)
        c.setFont("PF-It",33); c.setFillColor(ACC2); c.drawString(ML,H-75*mm,title2)
        c.setStrokeColor(ACCENT); c.setLineWidth(2); c.line(ML,H-84*mm,ML+28*mm,H-84*mm)
        c.setFont("Inter",11.5); c.setFillColor(colors.HexColor("#d9e2ec"))
        for i,ln in enumerate(lines): c.drawString(ML,H-96*mm-i*6.4*mm,ln)
        for i,(num,cap) in enumerate(figures):
            x=ML+i*56*mm
            c.setFont("Inter-XB",25); c.setFillColor(ACC2); c.drawString(x,H-150*mm,num)
            c.setFont("Inter",9); c.setFillColor(colors.HexColor("#a9b8c9")); c.drawString(x,H-157*mm,cap)
        c.setFont("Inter",9); c.setFillColor(colors.HexColor("#8fa0b3"))
        c.drawString(ML,MB+8*mm,footer_left)
        if for_whom:
            c.drawRightString(W-MR,MB+8*mm,for_whom)
        c.restoreState()
    return cover

def make_page(header_text, footer_left):
    def page(c,doc):
        c.saveState(); kicker(c,ML,H-14*mm,header_text,7,MUTED)
        c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(ML,H-17*mm,W-MR,H-17*mm)
        c.setFont("Inter",8); c.setFillColor(MUTED)
        c.drawRightString(W-MR,MB-6*mm,str(c.getPageNumber())); c.drawString(ML,MB-6*mm,footer_left)
        c.restoreState()
    return page

def build(path, story, cover_fn, page_fn, title):
    doc=BaseDocTemplate(path,pagesize=A4,leftMargin=ML,rightMargin=MR,topMargin=MT,bottomMargin=MB,
                        title=title,author="Maksi Studio")
    fr=Frame(ML,MB,W-ML-MR,H-MT-MB,id="f",leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover",frames=[fr],onPage=cover_fn),
                          PageTemplate(id="body",frames=[fr],onPage=page_fn)])
    doc.build(story)
    return path
