document.addEventListener('DOMContentLoaded', () => {
    /* ==========================================================================
       Language Switcher Logic
       ========================================================================== */
    const langToggle = document.getElementById('lang-toggle');
    const body = document.body;
    const pageTitle = document.getElementById('page-title');

    const titles = {
        pt: 'Ravi Mini Toolbar — Extensão para LibreOffice',
        en: 'Ravi Mini Toolbar — LibreOffice Extension'
    };

    function setLanguage(lang) {
        if (lang === 'en') {
            body.classList.remove('lang-pt');
            body.classList.add('lang-en');
            pageTitle.textContent = titles.en;
            document.documentElement.lang = 'en';
        } else {
            body.classList.remove('lang-en');
            body.classList.add('lang-pt');
            pageTitle.textContent = titles.pt;
            document.documentElement.lang = 'pt-BR';
        }
        localStorage.setItem('preferred-lang', lang);
    }

    // Load preferred or default language
    const savedLang = localStorage.getItem('preferred-lang') || 
                      (navigator.language.startsWith('en') ? 'en' : 'pt');
    setLanguage(savedLang);

    // Toggle language on click
    langToggle.addEventListener('click', () => {
        const currentLang = body.classList.contains('lang-pt') ? 'en' : 'pt';
        setLanguage(currentLang);
    });

    /* ==========================================================================
       Navbar Scroll Effect
       ========================================================================== */
    const navbar = document.getElementById('navbar');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    });

    /* ==========================================================================
       Interactive Text Formatting Simulator
       ========================================================================== */
    const editor = document.getElementById('editor-area');
    const toolbar = document.getElementById('interactive-toolbar');

    // UI Buttons
    const btnBold = document.getElementById('btn-bold');
    const btnItalic = document.getElementById('btn-italic');
    const btnUnderline = document.getElementById('btn-underline');
    const btnStrike = document.getElementById('btn-strike');
    const btnSuperscript = document.getElementById('btn-superscript');
    const btnSubscript = document.getElementById('btn-subscript');
    const btnClear = document.getElementById('btn-clear');
    
    // Fonts & Sizes
    const fontDropdown = document.getElementById('tb-font-dropdown');
    const currentFont = document.getElementById('current-font');
    const sizeDropdown = document.getElementById('tb-size-dropdown');
    const currentSize = document.getElementById('current-size');
    
    // Color & Highlights
    const fontColorBtn = document.getElementById('btn-font-color');
    const fontColorIndicator = document.getElementById('font-color-indicator');
    const fontColorPalette = document.getElementById('font-color-palette');
    const bgColorBtn = document.getElementById('btn-bg-color');
    const bgColorIndicator = document.getElementById('bg-color-indicator');
    const bgColorPalette = document.getElementById('bg-color-palette');

    // Alignment
    const btnAlign = document.getElementById('btn-align');
    const alignMenu = document.getElementById('align-menu');

    // State variable to store range
    let currentSelectionRange = null;

    // Check if selection is inside editor
    function isSelectionInEditor() {
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return false;
        
        const container = selection.getRangeAt(0).commonAncestorContainer;
        return editor.contains(container.nodeType === 3 ? container.parentNode : container);
    }

    // Save current range to restore if lost during click
    function saveSelection() {
        const selection = window.getSelection();
        if (selection.rangeCount > 0 && isSelectionInEditor()) {
            currentSelectionRange = selection.getRangeAt(0).cloneRange();
        }
    }

    function restoreSelection() {
        if (currentSelectionRange) {
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(currentSelectionRange);
        }
    }

    // Main Selection Event Listener
    function handleTextSelection() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (selectedText && isSelectionInEditor()) {
            saveSelection();
            
            // Calculate coordinates
            const range = selection.getRangeAt(0);
            const rects = range.getClientRects();
            if (rects.length > 0) {
                const rect = rects[0];
                
                // Position calculation relative to viewport
                const editorRect = editor.getBoundingClientRect();
                const containerRect = editor.parentNode.getBoundingClientRect();
                
                // Position toolbar horizontally centered below selection
                let left = rect.left - containerRect.left + (rect.width / 2) - (toolbar.offsetWidth / 2);
                let top = rect.bottom - containerRect.top + 8; // 8px gap below selection

                // Prevent toolbar overflow out of screen bounds
                if (window.innerWidth > 768) {
                    const maxLeft = containerRect.width - toolbar.offsetWidth - 16;
                    left = Math.max(16, Math.min(left, maxLeft));
                    
                    toolbar.style.left = `${left}px`;
                    toolbar.style.top = `${top}px`;
                }
                
                toolbar.classList.add('active');
                updateToolbarButtonStates();
            }
        } else {
            // Only hide toolbar if selection is truly empty and we are not interacting with the toolbar elements
            const activeEl = document.activeElement;
            if (!toolbar.contains(activeEl)) {
                hideToolbar();
            }
        }
    }

    function hideToolbar() {
        toolbar.classList.remove('active');
        closeAllDropdowns();
    }

    function closeAllDropdowns() {
        fontDropdown.classList.remove('active');
        sizeDropdown.classList.remove('active');
        fontColorPalette.parentNode.classList.remove('active');
        bgColorPalette.parentNode.classList.remove('active');
        alignMenu.parentNode.classList.remove('active');
    }

    // Monitor selection events
    document.addEventListener('selectionchange', handleTextSelection);
    editor.addEventListener('mouseup', handleTextSelection);
    editor.addEventListener('keyup', handleTextSelection);

    // Hide toolbar when clicking outside editor/toolbar
    document.addEventListener('mousedown', (e) => {
        if (!editor.contains(e.target) && !toolbar.contains(e.target)) {
            hideToolbar();
        }
    });

    /* ==========================================================================
       Format Execution Helpers (execCommand with selection safety)
       ========================================================================== */
    function format(command, value = null) {
        restoreSelection();
        document.execCommand(command, false, value);
        saveSelection();
        updateToolbarButtonStates();
    }

    // Highlight button states based on selection properties
    function updateToolbarButtonStates() {
        btnBold.classList.toggle('active', document.queryCommandState('bold'));
        btnItalic.classList.toggle('active', document.queryCommandState('italic'));
        btnUnderline.classList.toggle('active', document.queryCommandState('underline'));
        btnStrike.classList.toggle('active', document.queryCommandState('strikeThrough'));
        btnSuperscript.classList.toggle('active', document.queryCommandState('superscript'));
        btnSubscript.classList.toggle('active', document.queryCommandState('subscript'));
        
        // Update font name indicator
        try {
            const font = document.queryCommandValue('fontName').replace(/['"]/g, '');
            currentFont.textContent = font || 'Arial';
        } catch(e) {}

        // Update font size indicator
        try {
            const sizeMap = { '1': '10', '2': '12', '3': '14', '4': '16', '5': '18', '6': '24' };
            const sizeVal = document.queryCommandValue('fontSize');
            currentSize.textContent = sizeMap[sizeVal] || '12';
        } catch(e) {}
    }

    /* ==========================================================================
       Toolbar Button Listeners
       ========================================================================== */
    // Helper to prevent losing selection focus on click
    const preventLossOfFocus = (e) => {
        e.preventDefault();
        restoreSelection();
    };

    // Styling Buttons
    btnBold.addEventListener('mousedown', preventLossOfFocus);
    btnBold.addEventListener('click', () => format('bold'));

    btnItalic.addEventListener('mousedown', preventLossOfFocus);
    btnItalic.addEventListener('click', () => format('italic'));

    btnUnderline.addEventListener('mousedown', preventLossOfFocus);
    btnUnderline.addEventListener('click', () => format('underline'));

    btnStrike.addEventListener('mousedown', preventLossOfFocus);
    btnStrike.addEventListener('click', () => format('strikeThrough'));

    btnSuperscript.addEventListener('mousedown', preventLossOfFocus);
    btnSuperscript.addEventListener('click', () => format('superscript'));

    btnSubscript.addEventListener('mousedown', preventLossOfFocus);
    btnSubscript.addEventListener('click', () => format('subscript'));

    btnClear.addEventListener('mousedown', preventLossOfFocus);
    btnClear.addEventListener('click', () => format('removeFormat'));

    // Dropdowns click toggles
    fontDropdown.addEventListener('mousedown', preventLossOfFocus);
    fontDropdown.addEventListener('click', (e) => {
        const isActive = fontDropdown.classList.contains('active');
        closeAllDropdowns();
        if (!isActive) fontDropdown.classList.add('active');
    });

    sizeDropdown.addEventListener('mousedown', preventLossOfFocus);
    sizeDropdown.addEventListener('click', () => {
        const isActive = sizeDropdown.classList.contains('active');
        closeAllDropdowns();
        if (!isActive) sizeDropdown.classList.add('active');
    });

    fontColorBtn.addEventListener('mousedown', preventLossOfFocus);
    fontColorBtn.addEventListener('click', () => {
        const wrapper = fontColorBtn.parentNode;
        const isActive = wrapper.classList.contains('active');
        closeAllDropdowns();
        if (!isActive) wrapper.classList.add('active');
    });

    bgColorBtn.addEventListener('mousedown', preventLossOfFocus);
    bgColorBtn.addEventListener('click', () => {
        const wrapper = bgColorBtn.parentNode;
        const isActive = wrapper.classList.contains('active');
        closeAllDropdowns();
        if (!isActive) wrapper.classList.add('active');
    });

    btnAlign.addEventListener('mousedown', preventLossOfFocus);
    btnAlign.addEventListener('click', () => {
        const wrapper = btnAlign.parentNode;
        const isActive = wrapper.classList.contains('active');
        closeAllDropdowns();
        if (!isActive) wrapper.classList.add('active');
    });

    // Dropdowns Item Selection
    fontDropdown.querySelectorAll('.tb-dropdown-item').forEach(item => {
        item.addEventListener('mousedown', preventLossOfFocus);
        item.addEventListener('click', () => {
            const font = item.getAttribute('data-value');
            format('fontName', font);
            currentFont.textContent = font;
            fontDropdown.classList.remove('active');
        });
    });

    sizeDropdown.querySelectorAll('.tb-dropdown-item').forEach(item => {
        item.addEventListener('mousedown', preventLossOfFocus);
        item.addEventListener('click', () => {
            const size = item.getAttribute('data-value');
            const sizeMap = { '10': 1, '12': 2, '14': 3, '16': 4, '18': 5, '24': 6 };
            format('fontSize', sizeMap[size]);
            currentSize.textContent = size;
            sizeDropdown.classList.remove('active');
        });
    });

    fontColorPalette.querySelectorAll('.color-swatch').forEach(swatch => {
        swatch.addEventListener('mousedown', preventLossOfFocus);
        swatch.addEventListener('click', () => {
            const color = swatch.style.backgroundColor;
            format('foreColor', color);
            fontColorIndicator.style.backgroundColor = color;
            fontColorPalette.parentNode.classList.remove('active');
        });
    });

    bgColorPalette.querySelectorAll('.color-swatch').forEach(swatch => {
        swatch.addEventListener('mousedown', preventLossOfFocus);
        swatch.addEventListener('click', () => {
            const color = swatch.style.backgroundColor;
            format('hiliteColor', color);
            bgColorIndicator.style.backgroundColor = color;
            bgColorPalette.parentNode.classList.remove('active');
        });
    });

    alignMenu.querySelectorAll('.align-opt').forEach(opt => {
        opt.addEventListener('mousedown', preventLossOfFocus);
        opt.addEventListener('click', () => {
            const alignment = opt.getAttribute('data-align');
            if (alignment === 'left') format('justifyLeft');
            else if (alignment === 'center') format('justifyCenter');
            else if (alignment === 'right') format('justifyRight');
            else if (alignment === 'justify') format('justifyFull');
            alignMenu.parentNode.classList.remove('active');
        });
    });
});
