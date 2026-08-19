import asyncio, httpx, json, sys
sys.stdout.reconfigure(encoding='utf-8')

async def test_lookahead():
    url = 'http://127.0.0.1:8000/api/analyze/stream'
    payload = {
        'before_fen': '3rr1k1/bppq1pp1/p1n2n1p/3bpN2/8/2PP2NP/PPB2PP1/R1BQR1K1 b - - 5 16',
        'after_fen': '3rr1k1/bpp2pp1/p1n1qn1p/3bpN2/8/2PP2NP/PPB2PP1/R1BQR1K1 w - - 6 17',
        'move_san': 'Qe6',
        'move_uci': 'd7e6'
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        async with client.stream('POST', url, json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.startswith('data:'):
                    try:
                        ev = json.loads(line[5:])
                        if ev.get('event') == 'analysis':
                            data = ev.get('data')
                            print('=== LOOKAHEAD INSIGHT ===')
                            print(json.dumps(data.get('lookahead'), indent=2, ensure_ascii=False))
                            print('\n=== PV CANDIDATE LINES ===')
                            for pv in data.get('pv_lines', []):
                                print('Rank', pv.get('rank'), ':', pv.get('formatted_line'), '| Tip:', pv.get('narrative_summary'))
                        elif ev.get('event') == 'done':
                            print('\n=== STREAMED COMMENTARY ===')
                            print(ev.get('data', {}).get('full_commentary'))
                    except Exception as e:
                        pass

asyncio.run(test_lookahead())