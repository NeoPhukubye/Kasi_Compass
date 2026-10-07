// ---------------------------------------------------------------------
// Telkom Tower Puzzle Game — Data-free fun at Pretoria & Johannesburg.
// ---------------------------------------------------------------------

const TELKOM_STOPS = new Set(['pretoria', 'johannesburg_park']);

const PUZZLE_SIZES = {
    easy: { rows: 3, cols: 3 },
    medium: { rows: 4, cols: 4 },
    hard: { rows: 5, cols: 5 },
};

let puzzleState = {
    container: null,
    overlay: null,
    pieces: [],
    size: PUZZLE_SIZES.easy,
    moves: 0,
    startTime: null,
    timerInterval: null,
    isComplete: false,
    keyHandler: null,
    onClose: null,
};

function createPuzzlePiece(correctIndex, totalPieces, size, imgSrc) {
    // The background image is sized to cover the whole grid
    // (background-size = cols*100% rows*100%), so the piece that belongs at
    // grid position `correctIndex` shows the slice starting at that column /
    // row of the image. background-position is expressed as a percentage of the
    // *overflowing* image, hence col * 100 / cols (not cols - 1): for a 3x3
    // grid the correct positions are 0%, 33.3% and 66.7%.
    const col = correctIndex % size.cols;
    const row = Math.floor(correctIndex / size.cols);
    const x = col * (100 / size.cols);
    const y = row * (100 / size.rows);

    const piece = document.createElement('button');
    piece.className = 'puzzle-piece';
    piece.dataset.correctIndex = String(correctIndex);
    piece.style.cssText = `
        width: ${100 / size.cols}%;
        aspect-ratio: 1;
        background-image: url('${imgSrc}');
        background-size: ${size.cols * 100}% ${size.rows * 100}%;
        background-position: ${x}% ${y}%;
        border: 2px solid #1a472a;
        border-radius: 4px;
        cursor: pointer;
        touch-action: none;
    `;
    piece.setAttribute('aria-label', `Puzzle piece ${correctIndex + 1} of ${totalPieces}`);
    return piece;
}

function shuffleArray(array) {
    const shuffled = [...array];
    // Multiple shuffle passes for better mixing
    const passes = 3;
    for (let pass = 0; pass < passes; pass++) {
        for (let i = shuffled.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
        }
    }
    return shuffled;
}

function startTimer() {
    puzzleState.startTime = Date.now();
    puzzleState.timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - puzzleState.startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        const timerEl = puzzleState.container?.querySelector('.puzzle-timer');
        if (timerEl) {
            timerEl.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
        }
    }, 1000);
}

function stopTimer() {
    if (puzzleState.timerInterval) {
        clearInterval(puzzleState.timerInterval);
        puzzleState.timerInterval = null;
    }
}

function updateMoves() {
    const movesEl = puzzleState.container?.querySelector('.puzzle-moves');
    if (movesEl) {
        movesEl.textContent = puzzleState.moves;
    }
}

function checkWin() {
    // Win when every piece is back in the grid position it belongs at.
    return puzzleState.pieces.every((piece) => piece.dataset.displayIndex === piece.dataset.correctIndex);
}

function onPuzzleComplete() {
    puzzleState.isComplete = true;
    stopTimer();
    const elapsed = Math.floor((Date.now() - puzzleState.startTime) / 1000);
    const mins = Math.floor(elapsed / 60);
    const secs = elapsed % 60;

    setTimeout(() => {
        alert(`🎉 Puzzle Complete!\n\nTime: ${mins}:${secs.toString().padStart(2, '0')}\nMoves: ${puzzleState.moves}\n\nTelkom keeps you connected — even offline!`);
        closePuzzle();
    }, 300);
}

function swapPieces(piece1, piece2) {
    // Swap the two pieces' grid positions: physically exchange them in the DOM
    // (so each moves to the other's cell) and exchange their displayIndex
    // values, which track current position. correctIndex travels with the
    // piece and is what decides the image slice each cell shows, so the win
    // condition is displayIndex === correctIndex for every piece.
    const parent = piece1.parentNode;
    const index1 = Array.from(parent.children).indexOf(piece1);
    const index2 = Array.from(parent.children).indexOf(piece2);

    if (index1 < index2) {
        parent.insertBefore(piece2, piece1);
    } else {
        parent.insertBefore(piece1, piece2);
    }

    const temp = piece1.dataset.displayIndex;
    piece1.dataset.displayIndex = piece2.dataset.displayIndex;
    piece2.dataset.displayIndex = temp;

    puzzleState.moves++;
    updateMoves();

    if (checkWin()) {
        onPuzzleComplete();
    }
}

let selectedPiece = null;

function onPieceClick(piece) {
    if (puzzleState.isComplete) return;
    
    if (!selectedPiece) {
        selectedPiece = piece;
        piece.classList.add('selected');
    } else if (selectedPiece === piece) {
        selectedPiece.classList.remove('selected');
        selectedPiece = null;
    } else {
        selectedPiece.classList.remove('selected');
        swapPieces(selectedPiece, piece);
        selectedPiece = null;
    }
}

function createPuzzleGrid(size, imgSrc) {
    const grid = document.createElement('div');
    grid.className = 'puzzle-grid';
    grid.style.cssText = `
        display: grid;
        grid-template-columns: repeat(${size.cols}, 1fr);
        gap: 4px;
        max-width: 400px;
        aspect-ratio: 1;
        margin: 0 auto;
    `;

    const totalPieces = size.rows * size.cols;
    // `indices[i]` is the correctIndex of the piece that starts at display
    // position i. A solved puzzle (indices[i] === i for every i) is a
    // zero-move puzzle, so keep shuffling until at least 70% of pieces are
    // out of place — a puzzle that is already solved or nearly solved is a
    // bad first impression.
    let indices = shuffleArray(Array.from({ length: totalPieces }, (_, i) => i));
    let correctPositions = indices.filter((correctIndex, displayIndex) => correctIndex === displayIndex).length;
    let guard = 0;
    while (correctPositions > totalPieces * 0.3 && guard < 100) {
        indices = shuffleArray(Array.from({ length: totalPieces }, (_, i) => i));
        correctPositions = indices.filter((correctIndex, displayIndex) => correctIndex === displayIndex).length;
        guard++;
    }

    puzzleState.pieces = indices.map((correctIndex, displayIndex) => {
        const piece = createPuzzlePiece(correctIndex, totalPieces, size, imgSrc);
        // `displayIndex` is where this piece sits in the grid right now;
        // `correctIndex` is where it belongs. A swap exchanges displayIndex
        // between two pieces — the image slice each shows travels with its
        // correctIndex, so the win condition is displayIndex === correctIndex.
        piece.dataset.displayIndex = String(displayIndex);
        piece.addEventListener('click', () => onPieceClick(piece));
        // Touch support
        piece.addEventListener('touchstart', (e) => {
            e.preventDefault();
            onPieceClick(piece);
        }, { passive: false });
        grid.appendChild(piece);
        return piece;
    });

    return grid;
}

function closePuzzle() {
    stopTimer();
    if (puzzleState.keyHandler) {
        document.removeEventListener('keydown', puzzleState.keyHandler);
        puzzleState.keyHandler = null;
    }
    if (puzzleState.overlay) {
        puzzleState.overlay.remove();
        puzzleState.overlay = null;
    }
    puzzleState.container = null;
    puzzleState.pieces = [];
    puzzleState.moves = 0;
    puzzleState.startTime = null;
    puzzleState.isComplete = false;
    selectedPiece = null;
    if (puzzleState.onClose) {
        puzzleState.onClose();
        puzzleState.onClose = null;
    }
}

function openTelkomPuzzle(waypointId, onClose = null) {
    if (!TELKOM_STOPS.has(waypointId)) {
        console.log('Telkom puzzle only available at Pretoria and Johannesburg Park');
        return;
    }

    puzzleState.onClose = onClose;
    puzzleState.size = PUZZLE_SIZES.easy;
    puzzleState.moves = 0;
    puzzleState.isComplete = false;
    selectedPiece = null;

    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'puzzle-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.85);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 20px;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    `;

    const stopNames = {
        pretoria: 'Pretoria',
        johannesburg_park: 'Johannesburg Park Station (Telkom Tower)',
    };

    const container = document.createElement('div');
    container.className = 'puzzle-container';
    container.style.cssText = `
        background: white;
        border-radius: 16px;
        padding: 24px;
        max-width: 90vw;
        width: 440px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        animation: puzzle-pop-in 0.3s ease-out;
    `;

    puzzleState.container = container;
    puzzleState.overlay = overlay;

    const header = document.createElement('div');
    header.style.cssText = `
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
        border-bottom: 2px solid #e8e8e0;
        padding-bottom: 12px;
    `;

    header.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px;">
            <img src="assets/telkom.png" alt="Telkom" style="height: 40px; width: auto;">
            <div>
                <h3 style="margin: 0; color: #1a472a; font-size: 1.3rem;">${stopNames[waypointId]}</h3>
                <p style="margin: 4px 0 0; color: #666; font-size: 0.9rem;">Telkom Tower Puzzle</p>
            </div>
        </div>
        <button class="puzzle-close" aria-label="Close puzzle" style="
            background: none;
            border: none;
            font-size: 2rem;
            cursor: pointer;
            color: #666;
            line-height: 1;
            padding: 4px;
            min-width: 44px;
            min-height: 44px;
        ">✕</button>
    `;

    header.querySelector('.puzzle-close').addEventListener('click', closePuzzle);

    const stats = document.createElement('div');
    stats.className = 'puzzle-stats';
    stats.style.cssText = `
        display: flex;
        justify-content: space-around;
        margin-bottom: 16px;
        padding: 12px;
        background: #f5f5f0;
        border-radius: 8px;
        font-weight: 600;
        color: #1a472a;
    `;
    stats.innerHTML = `
        <div>Moves: <span class="puzzle-moves">0</span></div>
        <div>Time: <span class="puzzle-timer">0:00</span></div>
    `;

    const difficulty = document.createElement('div');
    difficulty.style.cssText = `
        display: flex;
        justify-content: center;
        gap: 8px;
        margin-bottom: 16px;
    `;
    difficulty.innerHTML = `
        <button class="puzzle-diff-btn" data-size="easy" style="padding: 8px 16px; border: 2px solid #1a472a; background: white; border-radius: 20px; cursor: pointer; font-weight: 600;">Easy (3×3)</button>
        <button class="puzzle-diff-btn" data-size="medium" style="padding: 8px 16px; border: 2px solid #1a472a; background: white; border-radius: 20px; cursor: pointer; font-weight: 600;">Medium (4×4)</button>
        <button class="puzzle-diff-btn" data-size="hard" style="padding: 8px 16px; border: 2px solid #1a472a; background: white; border-radius: 20px; cursor: pointer; font-weight: 600;">Hard (5×5)</button>
    `;

    difficulty.querySelectorAll('.puzzle-diff-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const newSize = PUZZLE_SIZES[btn.dataset.size];
            if (newSize.rows * newSize.cols !== puzzleState.size.rows * puzzleState.size.cols) {
                puzzleState.size = newSize;
                rebuildPuzzle();
            }
            difficulty.querySelectorAll('.puzzle-diff-btn').forEach(b => {
                b.style.background = 'white';
                b.style.color = '#1a472a';
            });
            btn.style.background = '#1a472a';
            btn.style.color = 'white';
        });
    });
    
    // Set easy as default active
    difficulty.querySelector('[data-size="easy"]').style.background = '#1a472a';
    difficulty.querySelector('[data-size="easy"]').style.color = 'white';

    const gridContainer = document.createElement('div');
    gridContainer.className = 'puzzle-grid-container';
    const grid = createPuzzleGrid(puzzleState.size, 'assets/telkom.png');
    gridContainer.appendChild(grid);

    const footer = document.createElement('p');
    footer.style.cssText = `
        margin-top: 16px;
        text-align: center;
        color: #666;
        font-size: 0.85rem;
        line-height: 1.4;
    `;
    footer.innerHTML = '💡 Tap two pieces to swap them. Works offline — no data needed!<br><strong>Telkom</strong> — Connecting South Africa';

    container.append(header, stats, difficulty, gridContainer, footer);
    overlay.appendChild(container);
    document.body.appendChild(overlay);

    // Close on overlay click (outside container)
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePuzzle();
    });

    // Keyboard support: two pieces can be selected with Tab/Shift+Tab and
    // swapped with Enter/Space, so the puzzle is playable without a mouse or
    // a touchscreen. Escape closes the overlay — handled by the same handler
    // so it is removed when the puzzle closes (no leak across sessions).
    const focusablePieces = puzzleState.pieces;
    let focusIndex = 0;
    function focusPiece(index) {
        focusIndex = (index + focusablePieces.length) % focusablePieces.length;
        focusablePieces[focusIndex].focus();
    }
    function handlePuzzleKeydown(e) {
        if (e.key === 'Tab' && !e.shiftKey) {
            e.preventDefault();
            focusPiece(focusIndex + 1);
        } else if (e.key === 'Tab' && e.shiftKey) {
            e.preventDefault();
            focusPiece(focusIndex - 1);
        } else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onPieceClick(focusablePieces[focusIndex]);
        } else if (e.key === 'Escape') {
            closePuzzle();
        }
    }
    puzzleState.keyHandler = handlePuzzleKeydown;
    document.addEventListener('keydown', handlePuzzleKeydown);
    focusPiece(0);

    startTimer();
}

function rebuildPuzzle() {
    const gridContainer = puzzleState.container?.querySelector('.puzzle-grid-container');
    if (!gridContainer) return;
    
    stopTimer();
    puzzleState.moves = 0;
    puzzleState.isComplete = false;
    selectedPiece = null;
    updateMoves();
    
    const grid = createPuzzleGrid(puzzleState.size, 'assets/telkom.png');
    gridContainer.innerHTML = '';
    gridContainer.appendChild(grid);
    startTimer();
}

// Expose globally
window.TelkomPuzzle = {
    open: openTelkomPuzzle,
    close: closePuzzle,
    isOpen: () => !!puzzleState.overlay,
};