import base64
FLAG_ICONS = {
    'en': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="40" fill="#012169"/>
        <path d="M0,0 l60,40 M60,0 l-60,40" stroke="#fff" stroke-width="6"/>
        <path d="M0,0 l60,40 M60,0 l-60,40" stroke="#C8102E" stroke-width="4"/>
        <path d="M30,0 v40 M0,20 h60" stroke="#fff" stroke-width="10"/>
        <path d="M30,0 v40 M0,20 h60" stroke="#C8102E" stroke-width="6"/>
    </svg>
    '''.encode()).decode(),
    'ru': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="13.33" fill="#fff"/>
        <rect y="13.33" width="60" height="13.33" fill="#0039A6"/>
        <rect y="26.66" width="60" height="13.33" fill="#D52B1E"/>
    </svg>
    '''.encode()).decode(),
    'zh': base64.b64encode('''
    <svg width="24" height="16" viewBox="0 0 60 40" xmlns="http://www.w3.org/2000/svg">
        <rect width="60" height="40" fill="#DE2910"/>
        <g fill="#FFDE00">
            <path d="M12,8 l2,6.5 l6,-2 l-4.5,5 l4.5,4 l-6,-1.5 l-2,6.5 l-2,-6.5 l-6,1.5 l4.5,-4 l-4.5,-5 l6,2 z"/>
            <path d="M24,4 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M30,8 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M24,14 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
            <path d="M30,18 l1,3 l3,-1 l-2,2.5 l2,2 l-3,-0.5 l-1,3 l-1,-3 l-3,0.5 l2,-2 l-2,-2.5 l3,1 z"/>
        </g>
    </svg>
    '''.encode()).decode()
}
