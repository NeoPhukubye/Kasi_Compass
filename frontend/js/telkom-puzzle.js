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
    onClose: null,
};

function createPuzzlePiece(index, totalPieces, size, imgSrc) {
    const pieceSize = 100 / size.cols;
    const row = Math.floor(index / size.cols);
    const col = index % size.cols;
    const bgPosX = -col * (100 / (size.cols - 1)) * (size.cols - 1) / (size.cols - 1) * 100 / (size.cols - 1); // This is wrong, let me recalculate
    
    // Correct background position calculation
    const pieceWidthPercent = 100 / (size.cols - 1);
    const pieceHeightPercent = 100 / (size.rows - 1);
    
    const x = col * pieceWidthPercent;
    const y = row * pieceHeightPercent;

    const piece = document.createElement('button');
    piece.className = 'puzzle-piece';
    piece.dataset.index = index;
    piece.dataset.correctIndex = index;
    piece.style.cssText = `
        width: ${pieceSize}%;
        aspect-ratio: 1;
        background-image: url('${imgSrc}');
        background-size: ${size.cols * 100}% ${size.rows * 100}%;
        background-position: ${x}% ${y}%;
        border: 2px solid #1a472a;
        border-radius: 4px;
        cursor: pointer;
        touch-action: none;
    `;
    piece.setAttribute('aria-label', `Puzzle piece ${index + 1} of ${totalPieces}`);
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
    return puzzleState.pieces.every((piece, index) => 
        parseInt(piece.dataset.index) === parseInt(piece.dataset.correctIndex)
    );
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
    const parent = piece1.parentNode;
    const index1 = Array.from(parent.children).indexOf(piece1);
    const index2 = Array.from(parent.children).indexOf(piece2);
    
    // Swap in DOM
    if (index1 < index2) {
        parent.insertBefore(piece2, piece1);
    } else {
        parent.insertBefore(piece1, piece2);
    }
    
    // Update data attributes
    const temp = piece1.dataset.index;
    piece1.dataset.index = piece2.dataset.index;
    piece2.dataset.index = temp;
    
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
    let indices = shuffleArray(Array.from({ length: totalPieces }, (_, i) => i));
    
    // Ensure puzzle is not already solved (0 moves needed) or nearly solved
    // Count how many pieces are already in correct position
    let correctPositions = indices.filter((correctIndex, displayIndex) => correctIndex === displayIndex).length;
    while (correctPositions > totalPieces * 0.3) { // No more than 30% in correct place
        indices = shuffleArray(Array.from({ length: totalPieces }, (_, i) => i));
        correctPositions = indices.filter((correctIndex, displayIndex) => correctIndex === displayIndex).length;
    }
    
    puzzleState.pieces = indices.map((correctIndex, displayIndex) => {
        const piece = createPuzzlePiece(displayIndex, totalPieces, size, imgSrc);
        piece.dataset.correctIndex = correctIndex;
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

    // Close on Escape key
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            closePuzzle();
            document.removeEventListener('keydown', handleEscape);
        }
    };
    document.addEventListener('keydown', handleEscape);

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