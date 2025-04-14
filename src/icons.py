import base64

settings_svg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="#333333" xmlns="http://www.w3.org/2000/svg">
  <path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/>
</svg>
'''
help_svg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#333333" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="10"/>
  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
  <line x1="12" y1="17" x2="12.01" y2="17"/>
</svg>
'''
trash_svg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#333333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <polyline points="3 6 5 6 21 6"/>
  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
  <line x1="10" y1="11" x2="10" y2="17"/>
  <line x1="14" y1="11" x2="14" y2="17"/>
</svg>
'''
swap_svg = '''
<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#333333" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
  <polyline points="17 1 21 5 17 9"/>
  <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
  <polyline points="7 23 3 19 7 15"/>
  <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
</svg>
'''

FLAG_ICONS = {
    'en': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="40" fill="#012169"/>
        <path d="M0,0 l60,40 M60,0 l-60,40" stroke="#fff" stroke-width="6"/>
        <path d="M0,0 l60,40 M60,0 l-60,40" stroke="#C8102E" stroke-width="4"/>
        <path d="M30,0 v40 M0,20 h60" stroke="#fff" stroke-width="10"/>
        <path d="M30,0 v40 M0,20 h60" stroke="#C8102E" stroke-width="6"/>
    </svg>
    '''.encode('utf-8')).decode('ascii'),
    'ru': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="13.33" fill="#fff"/>
        <rect y="13.33" width="60" height="13.33" fill="#0039A6"/>
        <rect y="26.66" width="60" height="13.33" fill="#D52B1E"/>
    </svg>
    '''.encode('utf-8')).decode('ascii'),
    'zh': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="40" fill="#DE2910"/>
        <g fill="#FFDE00">
            <path d="M12,8 l2,6.5 l6,-2 l-4.5,5 l4.5,4 l-6,-1.5 l-2,6.5 l-2,-6.5 l-6,1.5 l4.5,-4 l-4.5,-5 l6,2 z"/>
            <path d="M26,4 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M30,8 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M30,14 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M26,18 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
        </g>
    </svg>
    '''.encode('utf-8')).decode('ascii'),
    'pt_BR': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 30 20" xmlns="http://www.w3.org/2000/svg">
      <rect width="30" height="20" fill="#009B3A"/>
      <path d="M15 3 L 3 10 L 15 17 L 27 10 Z" fill="#FFCC29"/>
      <circle cx="15" cy="10" r="4.5" fill="#002776"/>
      <path d="M 11 10.5 A 4.5 4.5 0 0 1 19 10.5" stroke="#FFFFFF" stroke-width="1.2" fill="none"/>
    </svg>
    '''.encode('utf-8')).decode('ascii'),
    'settings': base64.b64encode(settings_svg.encode('utf-8')).decode('ascii'),
    'help': base64.b64encode(help_svg.encode('utf-8')).decode('ascii'),
    'trash': base64.b64encode(trash_svg.encode('utf-8')).decode('ascii'),
    'swap': base64.b64encode(swap_svg.encode('utf-8')).decode('ascii'),
}
