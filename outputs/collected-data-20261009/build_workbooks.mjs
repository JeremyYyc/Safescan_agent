import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook, SpreadsheetFile} from '@oai/artifact-tool';
const base = path.dirname(new URL(import.meta.url).pathname).replace(/^\/([A-Za-z]:)/, '$1');
for (const group of ['repair', 'student', 'general']) {
  const dir = path.join(base, group);
  const data = JSON.parse(await fs.readFile(path.join(dir, 'workbook_input.json'), 'utf8'));
  const wb = Workbook.create();
  for (const [key, title] of [['records','总表'],['images','图片索引']]) {
    const sh = wb.worksheets.add(title);
    const rows = data[key].map(row => row.map(v => typeof v === 'string' && v.startsWith('=') ? "'"+v : v));
    const range = sh.getRangeByIndexes(0,0,rows.length,rows[0].length);
    range.values = rows;
    range.format.font = {name:'Arial',size:11};
    range.format.verticalAlignment = 'center';
    range.format.columnWidth = 24;
    range.format.rowHeight = 32;
    range.format.wrapText = true;
    sh.showGridLines = false;
    const head = sh.getRangeByIndexes(0,0,1,rows[0].length);
    head.format.fill = '#234A60';
    head.format.font = {name:'Arial',bold:true,color:'#FFFFFF',size:11};
    head.format.rowHeight = 32;
    sh.freezePanes.freezeRows(1);
    sh.tables.add(range.address ?? (key==='records'?`A1:N${rows.length}`:`A1:H${rows.length}`),true, group+'_'+key);
    if(key==='records') {
      sh.getRange(`A1:A${rows.length}`).format.columnWidth=49;
      sh.getRange(`B1:B${rows.length}`).format.columnWidth=72;
      sh.getRange(`C1:G${rows.length}`).format.columnWidth=20;
      sh.getRange(`H1:H${rows.length}`).format.columnWidth=72;
      sh.getRange(`L1:N${rows.length}`).format.columnWidth=85;
    } else {
      sh.getRange(`A1:A${rows.length}`).format.columnWidth=76;
      sh.getRange(`B1:B${rows.length}`).format.columnWidth=46;
      sh.getRange(`E1:G${rows.length}`).format.columnWidth=90;
    }
    range.format.autofitRows();
  }
  wb.recalculate();
  console.log((await wb.inspect({kind:'table',range:'总表!A1:G4',include:'values',tableMaxRows:4,tableMaxCols:7,maxChars:1100})).ndjson);
  console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?',options:{useRegex:true,maxResults:10},maxChars:400})).ndjson);
  for(const title of ['总表','图片索引']) {
    const preview = await wb.render({sheetName:title,range:title==='总表'?'A1:G5':'A1:D5',scale:1,format:'png'});
    await fs.writeFile(path.join(base,group+'-'+(title==='总表'?'records':'images')+'.png'),new Uint8Array(await preview.arrayBuffer()));
  }
  await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(dir,'总表.xlsx'));
  console.log('EXPORTED',group);
}
