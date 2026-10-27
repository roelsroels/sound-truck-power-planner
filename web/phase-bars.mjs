/** Render phase loads without parsing inline CSS or HTML. */
export function renderPhaseBars(container, rows, format, translate){
  const document=container.ownerDocument;
  const element=(tag,className,text)=>{
    const node=document.createElement(tag);
    node.className=className;
    if(text!==undefined)node.textContent=text;
    return node;
  };
  container.replaceChildren(...rows.map(({phase,va,current,budget})=>{
    const percent=budget>0?100*va/budget:0;
    const width=Number.isFinite(percent)?Math.max(0,Math.min(100,percent)):0;
    const row=element('div','phase-row');
    const title=element('div','phase-title');
    title.append(
      element('span','',`${phase}: ${format(va/1000,2)} kVA / ${format(current,1)} A`),
      element('span','',translate(`${format(percent,0)}% of per-phase budget`))
    );
    const bar=element('div','bar');
    const fill=element('div','bar-fill'+(percent>100?' over':''));
    // Individual CSSOM properties are permitted by style-src-attr 'none'.
    // Do not replace this with a style attribute or cssText.
    fill.style.width=width+'%';
    bar.append(fill);row.append(title,bar);
    return row;
  }));
}
