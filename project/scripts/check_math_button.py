"""Exercise the real UI click handler with a small DOM/network harness.

Verification only: run using .venv-math Python (quickjs), not an app dependency.
The network responses here are simulated; real server conversion is checked separately.
"""
import json
from pathlib import Path
import re
import quickjs


def run_case(status,payload,expected):
    root=Path(__file__).resolve().parents[1];base=root/'src/level_bridge/ocr'
    ids=re.findall(r'id="([^"]+)"',(base/'templates/math.html').read_text(encoding='utf-8'))
    ctx=quickjs.Context()
    ctx.eval('''function node(){return {childNodes:[],checked:false,disabled:true,value:'',textContent:'',hidden:true,files:[],replaceChildren(){this.childNodes=[];},append(x){this.childNodes.push(x);},setAttribute(){},getContext(){return {drawImage(){},clearRect(){},strokeRect(){},fillText(){}};}};}
var nodes={};function Image(){this.naturalWidth=600;this.naturalHeight=400;Object.defineProperty(this,'src',{set(value){if(this.onload)this.onload();}});}
var document={getElementById(id){return nodes[id]||null;},querySelector(){return {content:'token'};},createElement(){return node();},createTextNode(text){var n=node();n.textContent=text;return n;}};
var location={search:''};function URLSearchParams(){this.get=function(){return null;};}
var URL={createObjectURL(){return 'blob:photo';},revokeObjectURL(){}};function FormData(){this.append=function(){};}
var window={addEventListener(){}};function AbortController(){this.signal={};this.abort=function(){};}
function setTimeout(){return 1;}function clearTimeout(){}
''')
    ctx.eval('for(var id of '+json.dumps(ids)+'){nodes[id]=node();}')
    ctx.eval((base/'static/vendor/katex/katex.min.js').read_text(encoding='utf-8'))
    ctx.eval((base/'static/math.js').read_text(encoding='utf-8'))
    ctx.eval(f'var responseStatus={status};var responseBody='+json.dumps(payload)+''';function fetch(){return Promise.resolve({ok:responseStatus===200,status:responseStatus,json(){return Promise.resolve(responseBody);}});}''')
    ctx.eval('nodes.mathFile.files=[{}];nodes.mathFile.onchange();nodes.autoExtract.onclick();')
    assert ctx.eval('nodes.autoExtract.textContent')=='Reading...'
    assert 'Reading your image' in ctx.eval('nodes.resultStatus.textContent')
    for _ in range(40):
        if not ctx.execute_pending_job():break
    message=ctx.eval('nodes.resultStatus.textContent')
    assert expected in message,message
    assert ctx.eval('nodes.autoExtract.textContent')=='Read image'
    assert ctx.eval('nodes.autoExtract.disabled') is False
    if status==200 and payload.get('blocks'):assert ctx.eval('nodes.mixedResults.hidden') is False


def main():
    block=dict(kind='text',text='A converted sentence.',bbox=[0,0,200,30],column=0,row=0)
    run_case(200,dict(blocks=[block],warnings=[],recognised_equations=0,equation_candidates=0,columns=1,duration_s=.1),'Done.')
    run_case(403,{},'expired')
    run_case(400,{'error':'Select a JPG or PNG.'},'Select a JPG or PNG.')
    run_case(200,{'blocks':[]},'No readable text')
    print('4 UI click checks passed: conversion, expired session, server error, empty result; loading state and retry verified.')


if __name__=='__main__':main()
