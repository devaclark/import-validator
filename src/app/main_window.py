"""Main application window for the Import Validator."""
import sys
import json
import logging
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, 
                               QHBoxLayout, QWidget, QFileDialog, QLineEdit, QLabel, 
                               QSplitter, QTextEdit, QProgressDialog, QTabWidget,
                               QScrollArea, QFrame, QTreeWidget, QTreeWidgetItem,
                               QStatusBar, QDialog, QCheckBox, QMessageBox, QToolBar)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, pyqtSlot, QObject, QSize
from PyQt6.QtGui import QFont, QPalette, QColor, QShortcut, QKeySequence
from PyQt6.Qsci import QsciScintilla, QsciLexerPython, QsciAPIs
import datetime

from ..validator.config import ImportValidatorConfig
from ..validator.validator import AsyncImportValidator
from .web_bridge import WebBridge
from .code_editor import CodeEditor
from .ui_components import DARK_THEME, SPLITTER_STYLE
# Set up logging using centralized configuration
logger = logging.getLogger(__name__)


class ImportValidatorApp:
    """Main application window for the Import Validator."""

    def __init__(self, validator=None):
        """Initialize the application window."""
        super().__init__()
        self.validator = validator
        self.app = QApplication.instance() or QApplication([])
        self.window = QMainWindow()
        self.window.setWindowTitle("Import Validator")
        self.window.setGeometry(100, 100, 1200, 800)
        self._setup_ui()
        
        # Store references to cleanup later
        self.web_view = None
        self.code_view = None
        self.bridge = None
        self.channel = None
        
        # Track WebView initialization
        self.web_view_loaded = False
        self.pending_graph_data = None
        
        # Initialize UI immediately
        self._setup_ui()
        
    def showEvent(self, event):
        """Handle window show event."""
        super().showEvent(event)
        if not self.web_view_loaded:
            self.web_view_loaded = True
            # Schedule the async WebView loading
            asyncio.create_task(self._load_web_view())
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Create main widget and layout
        main_widget = QWidget()
        self.window.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create top bar with minimal height
        top_bar = QWidget()
        top_bar.setMaximumHeight(32)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(4, 0, 4, 0)
        top_layout.setSpacing(4)
        
        # Path input and browse button
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select project folder...")
        self.path_input.setReadOnly(True)
        
        browse_button = QPushButton("Browse")
        browse_button.setFixedWidth(80)
        browse_button.clicked.connect(self.browse_folder)
        
        self.scan_button = QPushButton("Scan Project")
        self.scan_button.setFixedWidth(100)
        self.scan_button.setEnabled(False)
        self.scan_button.clicked.connect(self._scan_clicked)
        
        self.export_button = QPushButton("Export Data")
        self.export_button.setFixedWidth(100)
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(lambda: asyncio.create_task(self.export_validation_data()))
        
        top_layout.addWidget(self.path_input)
        top_layout.addWidget(browse_button)
        top_layout.addWidget(self.scan_button)
        top_layout.addWidget(self.export_button)
        
        layout.addWidget(top_bar)
        
        # Create main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(8)
        main_splitter.setChildrenCollapsible(False)
        
        # Create visualization panel with no margins
        viz_container = QWidget()
        viz_layout = QVBoxLayout(viz_container)
        viz_layout.setContentsMargins(0, 0, 0, 0)
        viz_layout.setSpacing(0)
        
        # Initialize WebView
        self.web_view = QWebEngineView()
        self.web_view.setMinimumWidth(800)
        
        # Set up web channel for Qt<->JavaScript communication
        self.channel = QWebChannel()
        self.bridge = WebBridge(self)
        self.channel.registerObject('bridge', self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        # Load the template immediately
        self.web_view.setHtml(self.get_d3_template(), QUrl("qrc:/"))
        
        viz_layout.addWidget(self.web_view)
        
        # Create right panel with tabs
        right_panel = QTabWidget()
        right_panel.setMinimumWidth(400)
        right_panel.setDocumentMode(True)
        
        # Details tab
        details_tab = QScrollArea()
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        details_layout.setContentsMargins(4, 4, 4, 4)
        details_layout.setSpacing(4)
        
        # File info section with minimal padding
        file_info_frame = QFrame()
        file_info_frame.setFrameStyle(QFrame.Shape.NoFrame)
        file_info_layout = QVBoxLayout(file_info_frame)
        file_info_layout.setContentsMargins(4, 4, 4, 4)
        file_info_layout.setSpacing(2)
        
        self.node_name = QLabel()
        self.node_name.setStyleSheet("font-size: 14px; font-weight: bold; padding: 0;")
        self.node_path = QLabel()
        self.node_path.setWordWrap(True)
        self.node_path.setStyleSheet("color: #888; font-size: 12px; padding: 0;")
        
        file_info_layout.addWidget(self.node_name)
        file_info_layout.addWidget(self.node_path)
        
        # Metrics section with minimal padding
        metrics_frame = QFrame()
        metrics_frame.setFrameStyle(QFrame.Shape.NoFrame)
        metrics_layout = QVBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(4, 4, 4, 4)
        metrics_layout.setSpacing(2)
        
        metrics_title = QLabel("Metrics")
        metrics_title.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0;")
        metrics_layout.addWidget(metrics_title)
        
        self.metrics_tree = QTreeWidget()
        self.metrics_tree.setHeaderLabels(["Metric", "Value"])
        self.metrics_tree.setColumnCount(2)
        self.metrics_tree.setAlternatingRowColors(True)
        self.metrics_tree.setStyleSheet("QTreeWidget { border: none; }")
        metrics_layout.addWidget(self.metrics_tree)
        
        # Imports section with minimal padding
        imports_frame = QFrame()
        imports_frame.setFrameStyle(QFrame.Shape.NoFrame)
        imports_layout = QVBoxLayout(imports_frame)
        imports_layout.setContentsMargins(4, 4, 4, 4)
        imports_layout.setSpacing(2)
        
        imports_title = QLabel("Imports Analysis")
        imports_title.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0;")
        imports_layout.addWidget(imports_title)
        
        self.imports_tree = QTreeWidget()
        self.imports_tree.setHeaderLabels(["Type", "Import"])
        self.imports_tree.setColumnCount(2)
        self.imports_tree.setAlternatingRowColors(True)
        self.imports_tree.setStyleSheet("QTreeWidget { border: none; }")
        imports_layout.addWidget(self.imports_tree)
        
        # Add sections to details layout
        details_layout.addWidget(file_info_frame)
        
        # Create vertical splitter for metrics and imports
        details_splitter = QSplitter(Qt.Orientation.Vertical)
        details_splitter.setHandleWidth(8)
        details_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #2d2d2d;
                border: 1px solid #37373d;
                height: 2px;
            }
            QSplitter::handle:hover {
                background-color: #37373d;
            }
        """)
        
        # Add metrics and imports to splitter
        details_splitter.addWidget(metrics_frame)
        details_splitter.addWidget(imports_frame)
        
        # Set initial sizes (40% metrics, 60% imports)
        details_splitter.setSizes([200, 300])
        
        # Add splitter to details layout
        details_layout.addWidget(details_splitter)
        
        details_tab.setWidget(details_widget)
        details_tab.setWidgetResizable(True)
        details_tab.setFrameStyle(QFrame.Shape.NoFrame)
        
        # Code tab with minimal padding
        code_tab = QWidget()
        code_layout = QVBoxLayout(code_tab)
        code_layout.setContentsMargins(0, 0, 0, 0)
        code_layout.setSpacing(0)
        
        # Create code editor
        self.code_view = CodeEditor()
        self.code_view.setReadOnly(False)
        monospace_font = QFont("Consolas", 10)
        self.code_view.setFont(monospace_font)
        self.code_view.setFrameStyle(QFrame.Shape.NoFrame)
        
        # Add toolbar first, then code editor
        code_layout.addWidget(self.code_view.toolbar)
        code_layout.addWidget(self.code_view)
        
        # Add tabs
        right_panel.addTab(details_tab, "Details")
        right_panel.addTab(code_tab, "Source")
        
        # Add panels to main splitter
        main_splitter.addWidget(viz_container)
        main_splitter.addWidget(right_panel)
        
        # Set initial splitter sizes (70% viz, 30% details)
        main_splitter.setSizes([int(self.window.width() * 0.7), int(self.window.width() * 0.3)])
        
        layout.addWidget(main_splitter)
        
        # Add minimal status bar
        self.status_bar = QStatusBar()
        self.status_bar.setMaximumHeight(20)
        self.window.setStatusBar(self.status_bar)
        
        # Apply dark theme
        self.window.setStyleSheet(DARK_THEME)
        
        # Make splitters more visible and draggable
        main_splitter.setHandleWidth(8)
        main_splitter.setStyleSheet(SPLITTER_STYLE)
        
        # Add pin buttons to panels
        viz_header = QWidget()
        viz_header_layout = QHBoxLayout(viz_header)
        viz_header_layout.setContentsMargins(4, 4, 4, 4)
        viz_pin_btn = QPushButton("📌")
        viz_pin_btn.setFixedSize(24, 24)
        viz_pin_btn.setCheckable(True)
        viz_header_layout.addStretch()
        viz_header_layout.addWidget(viz_pin_btn)
        
        details_header = QWidget()
        details_header_layout = QHBoxLayout(details_header)
        details_header_layout.setContentsMargins(4, 4, 4, 4)
        details_pin_btn = QPushButton("📌")
        details_pin_btn.setFixedSize(24, 24)
        details_pin_btn.setCheckable(True)
        details_header_layout.addStretch()
        details_header_layout.addWidget(details_pin_btn)
        
        # Add status bar info
        self.status_bar.showMessage("Ready")
        
        def update_status_bar():
            line, col = self.code_view.getCursorPosition()
            self.status_bar.showMessage(f"Line: {line + 1}, Column: {col + 1}")
        
        self.code_view.cursorPositionChanged.connect(update_status_bar)
    
    def get_d3_template(self):
        """Return the D3 template HTML content."""
        return '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <style>
        body {
            margin: 0;
            padding: 0;
            background-color: #1e1e1e;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
        }
        svg {
            width: 100%;
            height: 100%;
        }
        .node {
            cursor: pointer;
        }
        .node circle {
            stroke: #2d2d2d;
            stroke-width: 1.5px;
        }
        .node text {
            font: 10px sans-serif;
            fill: #d4d4d4;
            pointer-events: none;
        }
        .link {
            fill: none;
            stroke: #2d2d2d;
            stroke-width: 1.5px;
            opacity: 0.6;
        }
        .link.highlighted {
            stroke: #569cd6 !important;
            stroke-width: 2.5px !important;
            opacity: 1;
        }
        .invalid {
            stroke: #f48771 !important;
        }
        .circular {
            stroke: #cca700 !important;
        }
        .selected {
            stroke: #569cd6 !important;
            stroke-width: 4px !important;
        }
        .selected circle {
            stroke: #569cd6 !important;
            stroke-width: 4px !important;
            filter: drop-shadow(0 0 8px rgba(86, 156, 214, 0.9));
            r: 12;
        }
        .selected text {
            fill: #569cd6 !important;
            font-weight: bold;
            font-size: 13px;
        }
        .related circle {
            stroke: #4ec9b0 !important;
            stroke-width: 2px !important;
            opacity: 0.9;
            r: 8;
        }
        .related text {
            fill: #4ec9b0 !important;
            font-size: 11px;
            font-weight: 500;
        }
        .dimmed {
            opacity: 0.08;
        }
        .dimmed text {
            opacity: 0.08;
        }
        .controls {
            position: absolute;
            top: 10px;
            right: 10px;
            background: rgba(45, 45, 45, 0.8);
            padding: 10px;
            border-radius: 4px;
            color: #d4d4d4;
        }
        .search-box {
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(45, 45, 45, 0.8);
            padding: 10px;
            border-radius: 4px;
            color: #d4d4d4;
        }
        .search-box input {
            background: #37373d;
            border: none;
            color: #d4d4d4;
            padding: 5px;
            width: 200px;
            margin-bottom: 5px;
        }
        .search-results {
            max-height: 200px;
            overflow-y: auto;
        }
        .search-result {
            padding: 4px;
            cursor: pointer;
        }
        .search-result:hover {
            background: #37373d;
        }
        .controls button {
            background: #37373d;
            border: none;
            color: #d4d4d4;
            padding: 5px 10px;
            margin: 2px;
            cursor: pointer;
            border-radius: 2px;
        }
        .controls button:hover {
            background: #3d3d42;
        }
    </style>
</head>
<body>
    <svg></svg>
    <div class="search-box">
        <input type="text" id="searchInput" placeholder="Search nodes...">
        <div class="search-results" id="searchResults"></div>
    </div>
    <div class="controls">
        <button onclick="resetZoom()">Reset View</button>
        <button onclick="toggleLabels()">Toggle Labels</button>
        <button onclick="togglePhysics()">Toggle Physics</button>
    </div>
    <script>
        let svg = d3.select("svg");
        let width = window.innerWidth;
        let height = window.innerHeight;
        let bridge;
        let selectedNode = null;
        let simulation = null;
        let showLabels = true;
        let physicsEnabled = true;
        let graphData = null;

        // Initialize WebChannel for Qt communication
        new QWebChannel(qt.webChannelTransport, function(channel) {
            bridge = channel.objects.bridge;
            console.log("WebChannel initialized");
        });

        // Set up SVG
        svg.attr("width", width)
           .attr("height", height);

        // Add zoom behavior
        let zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                container.attr("transform", event.transform);
            });

        svg.call(zoom);

        // Add arrow marker definitions
        svg.append("defs").selectAll("marker")
            .data(["arrow", "arrow-invalid", "arrow-circular", "arrow-highlighted"])
            .enter().append("marker")
            .attr("id", d => d)
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 20)
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-5L10,0L0,5")
            .attr("fill", d => d === "arrow" ? "#2d2d2d" : 
                              d === "arrow-invalid" ? "#f48771" : 
                              d === "arrow-highlighted" ? "#569cd6" : "#cca700");

        // Create container for zoom
        let container = svg.append("g");

        function updateGraph(data) {
            console.log("Updating graph with data:", data);
            graphData = data;
            
            // Clear previous graph
            container.selectAll("*").remove();

            // Create force simulation
            simulation = d3.forceSimulation(data.nodes)
                .force("link", d3.forceLink(data.links)
                    .id(d => d.id)
                    .distance(100))
                .force("charge", d3.forceManyBody()
                    .strength(-300)
                    .distanceMax(500))
                .force("center", d3.forceCenter(width / 2, height / 2))
                .force("collide", d3.forceCollide().radius(50));

            // Create links with curved paths
            const links = container.append("g")
                .selectAll("path")
                .data(data.links)
                .join("path")
                .attr("class", d => `link ${d.invalid ? 'invalid' : ''} ${d.circular ? 'circular' : ''}`)
                .attr("marker-end", d => d.invalid ? "url(#arrow-invalid)" : 
                                      d.circular ? "url(#arrow-circular)" : "url(#arrow)");

            // Create nodes
            const nodes = container.append("g")
                .selectAll(".node")
                .data(data.nodes)
                .join("g")
                .attr("class", "node")
                .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended));

            // Add circles to nodes
            nodes.append("circle")
                .attr("r", 8)
                .attr("fill", d => d.invalid ? "#f48771" : 
                                 d.circular ? "#cca700" : "#4ec9b0")
                .on("click", clicked);

            // Add labels to nodes
            const labels = nodes.append("text")
                .attr("dx", 12)
                .attr("dy", ".35em")
                .text(d => d.name)
                .style("display", showLabels ? null : "none");

            // Update positions on tick
            simulation.on("tick", () => {
                links.attr("d", d => {
                    const dx = d.target.x - d.source.x;
                    const dy = d.target.y - d.source.y;
                    const dr = Math.sqrt(dx * dx + dy * dy) * 2; // Curve factor
                    return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
                });

                nodes.attr("transform", d => `translate(${d.x},${d.y})`);
            });

            // Auto-zoom to fit all nodes after a short delay
            setTimeout(() => {
                const bounds = container.node().getBBox();
                const scale = 0.8 / Math.max(bounds.width / width, bounds.height / height);
                const transform = d3.zoomIdentity
                    .translate(width/2 - bounds.x * scale - bounds.width * scale/2,
                              height/2 - bounds.y * scale - bounds.height * scale/2)
                    .scale(scale);
                
                svg.transition()
                   .duration(750)
                   .call(zoom.transform, transform);
            }, 500);

            // Set up search functionality
            setupSearch(data.nodes);
        }

        function setupSearch(nodes) {
            const searchInput = document.getElementById('searchInput');
            const searchResults = document.getElementById('searchResults');

            searchInput.addEventListener('input', (e) => {
                const searchTerm = e.target.value.toLowerCase();
                if (!searchTerm) {
                    searchResults.innerHTML = '';
                    return;
                }

                const matches = nodes.filter(node => 
                    node.name.toLowerCase().includes(searchTerm) ||
                    node.full_path.toLowerCase().includes(searchTerm)
                ).slice(0, 10);

                searchResults.innerHTML = matches.map(node => {
                    // Escape the node ID for JavaScript string by encoding it
                    const escapedId = encodeURIComponent(node.id);
                    return `
                        <div class="search-result" onclick="selectNode(decodeURIComponent('${escapedId}'))">
                            <strong>${node.name}</strong><br>
                            <small style="color: #888;">${node.full_path}</small>
                        </div>
                    `;
                }).join('');
            });
        }

        function selectNode(nodeId) {
            const node = graphData.nodes.find(n => n.id === nodeId);
            if (node) {
                // Clear search results and input
                document.getElementById('searchResults').innerHTML = '';
                document.getElementById('searchInput').value = '';
                
                // Remove previous selection
                container.selectAll("circle").classed("selected", false);
                container.selectAll(".node").classed("related", false).classed("dimmed", false);
                container.selectAll(".link")
                    .classed("highlighted", false)
                    .classed("dimmed", false)
                    .attr("marker-end", l => l.invalid ? "url(#arrow-invalid)" : 
                                          l.circular ? "url(#arrow-circular)" : "url(#arrow)");
                
                // Add selection to clicked node
                container.selectAll(".node")
                    .filter(d => d.id === nodeId)
                    .select("circle")
                    .classed("selected", true);
                
                // Get related nodes
                const relatedNodes = getRelatedNodes(node);
                
                // Highlight related nodes and links
                container.selectAll(".node").classed("dimmed", n => 
                    !relatedNodes.has(n.id) && n.id !== node.id
                );
                container.selectAll(".node").classed("related", n => 
                    relatedNodes.has(n.id)
                );
                container.selectAll(".link")
                    .classed("highlighted", link => link.source.id === node.id || link.target.id === node.id)
                    .classed("dimmed", link => link.source.id !== node.id && link.target.id !== node.id)
                    .attr("marker-end", link => {
                        if (link.source.id === node.id || link.target.id === node.id) {
                            return "url(#arrow-highlighted)";
                        }
                        return link.invalid ? "url(#arrow-invalid)" : 
                               link.circular ? "url(#arrow-circular)" : "url(#arrow)";
                    });
                
                // Notify Qt
                if (bridge) {
                    bridge.nodeSelected(JSON.stringify(node));
                    bridge.loadFileContents(node.full_path);
                }
                
                // Center view on selected node with animation
                const transform = d3.zoomIdentity
                    .translate(width/2 - node.x, height/2 - node.y)
                    .scale(1);
                
                svg.transition()
                   .duration(750)
                   .call(zoom.transform, transform);
            }
        }

        function getRelatedNodes(node) {
            const related = new Set();
            graphData.links.forEach(link => {
                if (link.source.id === node.id) {
                    related.add(link.target.id);
                } else if (link.target.id === node.id) {
                    related.add(link.source.id);
                }
            });
            return related;
        }

        function clicked(event, d) {
            // Remove previous selection
            container.selectAll("circle").classed("selected", false);
            container.selectAll(".node").classed("related", false).classed("dimmed", false);
            container.selectAll(".link")
                .classed("highlighted", false)
                .classed("dimmed", false)
                .attr("marker-end", l => l.invalid ? "url(#arrow-invalid)" : 
                                      l.circular ? "url(#arrow-circular)" : "url(#arrow)");
            
            // Add selection to clicked node
            d3.select(event ? event.target : null).classed("selected", true);
            selectedNode = d;

            // Get related nodes
            const relatedNodes = getRelatedNodes(d);

            // Highlight related nodes and links
            container.selectAll(".node").classed("dimmed", node => 
                !relatedNodes.has(node.id) && node.id !== d.id
            );
            container.selectAll(".node").classed("related", node => 
                relatedNodes.has(node.id)
            );
            container.selectAll(".link")
                .classed("highlighted", link => link.source.id === d.id || link.target.id === d.id)
                .classed("dimmed", link => link.source.id !== d.id && link.target.id !== d.id)
                .attr("marker-end", link => {
                    if (link.source.id === d.id || link.target.id === d.id) {
                        return "url(#arrow-highlighted)";
                    }
                    return link.invalid ? "url(#arrow-invalid)" : 
                           link.circular ? "url(#arrow-circular)" : "url(#arrow)";
                });

            // Notify Qt
            if (bridge) {
                bridge.nodeSelected(JSON.stringify(d));
                bridge.loadFileContents(d.full_path);
            }

            // Center view on selected node
            const transform = d3.zoomIdentity
                .translate(width/2 - d.x, height/2 - d.y)
                .scale(1);
            
            svg.transition()
               .duration(750)
               .call(zoom.transform, transform);
        }

        function dragstarted(event) {
            if (!event.active && physicsEnabled) simulation.alphaTarget(0.3).restart();
            event.subject.fx = event.subject.x;
            event.subject.fy = event.subject.y;
        }

        function dragged(event) {
            event.subject.fx = event.x;
            event.subject.fy = event.y;
        }

        function dragended(event) {
            if (!event.active && physicsEnabled) simulation.alphaTarget(0);
            event.subject.fx = null;
            event.subject.fy = null;
        }

        function resetZoom() {
            svg.transition()
               .duration(750)
               .call(zoom.transform, d3.zoomIdentity);
        }

        function toggleLabels() {
            showLabels = !showLabels;
            container.selectAll(".node text")
                    .style("display", showLabels ? null : "none");
        }

        function togglePhysics() {
            if (simulation) {
                physicsEnabled = !physicsEnabled;
                simulation.alpha(physicsEnabled ? 1 : 0);
                simulation.alphaTarget(physicsEnabled ? 0.3 : 0).restart();
            }
        }

        // Handle window resize
        window.addEventListener('resize', () => {
            width = window.innerWidth;
            height = window.innerHeight;
            svg.attr("width", width)
               .attr("height", height);
            if (simulation) {
                simulation.force("center", d3.forceCenter(width / 2, height / 2));
                simulation.alpha(1).restart();
            }
        });

        // Add background click handler to svg
        svg.on("click", (event) => {
            // Only handle clicks directly on the SVG background
            if (event.target === svg.node()) {
                // Clear selection
                container.selectAll("circle").classed("selected", false);
                container.selectAll(".node").classed("related", false).classed("dimmed", false);
                container.selectAll(".link")
                    .classed("highlighted", false)
                    .classed("dimmed", false)
                    .attr("marker-end", l => l.invalid ? "url(#arrow-invalid)" : 
                                          l.circular ? "url(#arrow-circular)" : "url(#arrow)");
                
                // Reset selected node
                selectedNode = null;
                
                // Notify Qt of deselection
                if (bridge) {
                    bridge.nodeSelected(JSON.stringify({}));
                }
            }
        });
    </script>
</body>
</html>
'''

    async def _load_web_view(self):
        """Load the D3 template asynchronously."""
        if not self.web_view:
            return
            
        try:
            # Create a future to track when the page is loaded
            page_loaded = asyncio.Future()
            
            def handle_load_finished(ok):
                if not page_loaded.done():
                    if ok:
                        self.web_view_loaded = True
                        # If there's pending data, display it now
                        if self.pending_graph_data:
                            self.update_visualization(self.pending_graph_data)
                            self.pending_graph_data = None
                    page_loaded.set_result(ok)
            
            # Connect the loadFinished signal
            self.web_view.loadFinished.connect(handle_load_finished)
            
            # Set the HTML content
            self.web_view.setHtml(self.get_d3_template(), QUrl("qrc:/"))
            
            # Wait for the page to load with a timeout
            try:
                await asyncio.wait_for(page_loaded, timeout=5.0)
            except asyncio.TimeoutError:
                print("Warning: WebView load timed out")
            finally:
                # Always disconnect the signal
                if self.web_view:
                    try:
                        self.web_view.loadFinished.disconnect(handle_load_finished)
                    except Exception:
                        pass
            
        except Exception as e:
            print(f"Error loading template: {e}")
    
    def browse_folder(self):
        """Open a file dialog to browse for project folder."""
        folder = QFileDialog.getExistingDirectory(self.window, "Select Project Folder")
        if folder:
            self.path_input.setText(folder)
            self.scan_button.setEnabled(True)
    
    def _scan_clicked(self):
        """Handle scan button click by scheduling the async scan."""
        asyncio.create_task(self.scan_project())
    
    async def scan_project(self):
        """Handle scan button click by scheduling the async scan."""
        try:
            if not self.path_input.text():
                logger.debug("No project path provided, skipping scan")
                return
                
            project_path = Path(self.path_input.text())
            logger.debug(f"Starting project scan for path: {project_path}")
            
            # Show progress dialog
            progress = QProgressDialog("Scanning project...", None, 0, 100, self.window)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            logger.debug("Created and showed progress dialog")
            
            try:
                # Look for requirements.txt and pyproject.toml in the project directory
                requirements_file = project_path / "requirements.txt"
                pyproject_file = project_path / "pyproject.toml"
                logger.debug(f"Checking for requirements files: requirements.txt exists: {requirements_file.exists()}, pyproject.toml exists: {pyproject_file.exists()}")
                
                # Create validator config with proper package detection
                logger.debug("Creating validator config")
                config = ImportValidatorConfig(
                    base_dir=str(project_path),
                    requirements_file=requirements_file if requirements_file.exists() else None,
                    pyproject_file=pyproject_file if pyproject_file.exists() else None,
                    ignore_patterns={"*.pyc", "__pycache__/*"},
                    complexity_threshold=10.0,
                    max_edges_per_diagram=100
                )
                logger.debug("Successfully created validator config")
                
                await asyncio.sleep(0)  # Allow UI to update
                progress.setValue(20)
                
                # Initialize validator
                logger.debug("Initializing validator")
                self.validator = AsyncImportValidator(config=config)
                await self.validator.initialize()
                logger.debug("Successfully initialized validator")
                
                await asyncio.sleep(0)  # Allow UI to update
                progress.setValue(40)
                
                # Run validation
                logger.debug("Starting validation")
                results = await self.validator.validate_all()
                logger.debug(f"Validation complete. Found {len(results.imports)} files with imports")
                
                await asyncio.sleep(0)  # Allow UI to update
                progress.setValue(60)
                
                # Convert results to graph data
                logger.debug("Converting results to graph data")
                graph_data = await self.convert_to_graph_data(results)
                logger.debug(f"Graph data conversion complete. Created {len(graph_data.get('nodes', []))} nodes and {len(graph_data.get('links', []))} links")
                
                await asyncio.sleep(0)  # Allow UI to update
                progress.setValue(80)
                
                # Update visualization
                logger.debug("Updating visualization")
                self.update_visualization(graph_data)
                logger.debug("Visualization update complete")
                
                # Enable export button after successful validation
                self.export_button.setEnabled(True)
                logger.debug("Enabled export button")
                
                await asyncio.sleep(0)  # Allow UI to update
                progress.setValue(100)
                
            except Exception as e:
                logger.error(f"Error during project scan: {str(e)}", exc_info=True)
                progress.close()
                # Show error dialog
                error_msg = f"Error scanning project: {str(e)}\n\nCheck import_validator.log for details."
                QMessageBox.critical(self.window, "Error", error_msg)
                # Disable export button on error
                self.export_button.setEnabled(False)
            finally:
                progress.close()
                
        except Exception as outer_e:
            logger.error(f"Outer error in scan_project: {str(outer_e)}", exc_info=True)
            QMessageBox.critical(self.window, "Error", f"Error in scan_project: {str(outer_e)}\n\nCheck import_validator.log for details.")
    
    async def convert_to_graph_data(self, results):
        nodes = []
        links = []
        node_ids = set()
        path_mapping = {}
        module_mapping = {}
        
        # First pass: Create nodes and build module mappings
        for file_path in results.imports.keys():
            file_path_obj = Path(file_path)
            normalized_path = str(file_path_obj)
            path_mapping[str(file_path)] = normalized_path
            node_ids.add(normalized_path)
            
            try:
                relative_to_base = file_path_obj.relative_to(Path(self.validator.base_dir))
                module_path = str(relative_to_base).replace('\\', '/').replace('/', '.').replace('.py', '')
                module_mapping[module_path] = normalized_path
                
                # Add mapping for directory when this is __init__.py
                if file_path_obj.name == '__init__.py':
                    dir_module_path = str(relative_to_base.parent).replace('\\', '/').replace('/', '.')
                    if dir_module_path:  # Only add if not empty
                        module_mapping[dir_module_path] = normalized_path
                        # Also map the full path for direct imports of the package
                        module_mapping[module_path.rsplit('.', 1)[0]] = normalized_path
                
                # Add mapping for the file itself without .py extension
                file_module_path = str(relative_to_base).replace('\\', '/').replace('/', '.')[:-3]  # Remove .py
                if file_module_path:
                    module_mapping[file_module_path] = normalized_path
                
                # Add mapping for each submodule level
                parts = module_path.split('.')
                for i in range(len(parts)):
                    submodule = '.'.join(parts[:i+1])
                    if submodule and not submodule in module_mapping:
                        module_mapping[submodule] = normalized_path
                
            except ValueError:
                logger.warning(f"Could not get relative path for {file_path} from {self.validator.base_dir}")
                continue
            
            node = {
                'id': normalized_path,
                'name': file_path_obj.name,
                'full_path': normalized_path,
                'module_path': module_path,
                'imports': list(results.imports.get(str(file_path), set())),
                'invalid_imports': list(results.invalid_imports.get(str(file_path), set())),
                'relative_imports': list(results.relative_imports.get(str(file_path), set())),
                'invalid': bool(results.invalid_imports.get(str(file_path), set())),
                'circular': normalized_path in results.circular_refs
            }
            nodes.append(node)
            logger.debug(f"Created node for {normalized_path} with module_path {module_path}")
        
        # Second pass: Create links using module resolution
        for source, imports in results.imports.items():
            source_path = path_mapping.get(str(source))
            if not source_path or source_path not in node_ids:
                continue
                
            source_dir = Path(source).parent
            source_file_obj = Path(source)
            
            try:
                source_relative = source_file_obj.relative_to(Path(self.validator.base_dir))
                source_module = str(source_relative).replace('\\', '/').replace('/', '.')[:-3]  # Remove .py
            except ValueError:
                logger.warning(f"Could not get relative path for source {source}")
                continue
            
            for imp in imports:
                # Skip stdlib and third-party imports
                if not imp.startswith('.'):
                    base_module = imp.split('.')[0]
                    if self.validator._classify_import(base_module, source) in ['stdlib', 'thirdparty']:
                        continue
                
                try:
                    target_path = None
                    
                    # Handle relative imports
                    if imp.startswith('.'):
                        # Count leading dots to determine how many levels up to go
                        dots = len(imp) - len(imp.lstrip('.'))
                        # Get the module part after the dots
                        imp_module = imp[dots:]
                        # Start from the source module
                        current_module = source_module
                        # Go up the required number of levels
                        for _ in range(dots):
                            current_module = '.'.join(current_module.split('.')[:-1])
                        
                        # Try to resolve the import
                        if imp_module:
                            # First try the full resolved path
                            resolved_module = f"{current_module}.{imp_module}" if current_module else imp_module
                            target_path = module_mapping.get(resolved_module)
                            
                            if not target_path:
                                # Try each part of the import path
                                parts = imp_module.split('.')
                                current_parts = current_module.split('.') if current_module else []
                                
                                for i in range(len(parts)):
                                    test_module = '.'.join(current_parts + parts[:i+1])
                                    if test_module in module_mapping:
                                        target_path = module_mapping[test_module]
                                        # For multi-part imports, prefer exact matches
                                        if i == len(parts) - 1:
                                            break
                        else:
                            # Just the current module (import from parent)
                            target_path = module_mapping.get(current_module)
                    else:
                        # For absolute imports, try different variations
                        target_path = module_mapping.get(imp)
                        if not target_path and '.' in imp:
                            # Try each part of the import path
                            parts = imp.split('.')
                            for i in range(len(parts)):
                                partial_import = '.'.join(parts[:i+1])
                                if partial_import in module_mapping:
                                    target_path = module_mapping[partial_import]
                                    # For multi-part imports, prefer exact matches
                                    if i == len(parts) - 1:
                                        break
                    
                    if target_path and target_path in node_ids:
                        # Create the link
                        link = {
                            'source': source_path,
                            'target': target_path,
                            'invalid': imp in results.invalid_imports.get(str(source), set()),
                            'circular': any(imp in cycle for cycle in results.circular_refs.get(str(source), []))
                        }
                        links.append(link)
                        logger.debug(f"Created link from {source_path} to {target_path} for import {imp}")
                    else:
                        logger.debug(f"Could not create link for import {imp} from {source_path} - target_path: {target_path}, module_mapping: {module_mapping}")
                except Exception as e:
                    logger.debug(f"Error processing import {imp} from {source}: {e}")
                    continue

        return {'nodes': nodes, 'links': links}
    
    def update_visualization(self, graph_data):
        """Update the visualization with graph data."""
        js_code = f"if (typeof updateGraph === 'function') {{ console.log('Calling updateGraph'); updateGraph({json.dumps(graph_data)}); }}"
        self.web_view.page().runJavaScript(js_code)
    
    def update_node_details(self, node_data):
        """Update the details panel with node information."""
        if not node_data:
            # Clear all fields when no node is selected
            self.node_name.setText("")
            self.node_path.setText("")
            self.metrics_tree.clear()
            self.imports_tree.clear()
            return
            
        # Update basic info
        self.node_name.setText(node_data.get('name', ''))
        self.node_path.setText(node_data.get('full_path', ''))
        
        # Update metrics tree
        self.metrics_tree.clear()
        metrics = [
            ("Total Imports", len(node_data.get('imports', []))),
            ("Invalid Imports", len(node_data.get('invalid_imports', []))),
            ("Relative Imports", len(node_data.get('relative_imports', []))),
            ("Has Circular Refs", "Yes" if node_data.get('circular') else "No"),
            ("Is Invalid", "Yes" if node_data.get('invalid') else "No")
        ]
        
        for metric, value in metrics:
            item = QTreeWidgetItem([metric, str(value)])
            if "Invalid" in metric and value != "0" and value != "No":
                item.setForeground(1, QColor("#f48771"))  # Softer red
            elif "Circular" in metric and value == "Yes":
                item.setForeground(1, QColor("#cca700"))  # Softer yellow
            self.metrics_tree.addTopLevelItem(item)
        
        # Update imports tree
        self.imports_tree.clear()
        
        # Standard imports
        if node_data.get('imports'):
            std_imports = QTreeWidgetItem(["Standard Imports", "Package/Module"])
            std_imports.setForeground(0, QColor("#4ec9b0"))  # Soft teal
            for imp in node_data['imports']:
                if not imp.startswith('.') and imp not in node_data.get('invalid_imports', []):
                    base_module = imp.split('.')[0]
                    details = "Standard Library" if base_module in self.validator.stdlib_modules else (
                        "External Package" if base_module in self.validator.config.valid_packages else "Project Module"
                    )
                    item = QTreeWidgetItem([imp, details])
                    item.setForeground(0, QColor("#9cdcfe"))  # Soft blue
                    std_imports.addChild(item)
            if std_imports.childCount() > 0:
                self.imports_tree.addTopLevelItem(std_imports)
        
        # Relative imports
        if node_data.get('relative_imports'):
            rel_imports = QTreeWidgetItem(["Relative Imports", "Resolution"])
            rel_imports.setForeground(0, QColor("#dcdcaa"))  # Soft gold
            for imp in node_data['relative_imports']:
                # Count leading dots to determine how many levels up
                dots = len(imp) - len(imp.lstrip('.'))
                imp_module = imp[dots:]  # Get the module part after the dots
                
                if dots == 1 and not imp_module:
                    resolution = "Current Package"
                elif dots == 1:
                    resolution = "Same Package"
                else:
                    up_levels = "." * dots
                    if imp_module:
                        resolution = f"{up_levels} ({dots} levels up) → {imp_module}"
                    else:
                        resolution = f"{up_levels} ({dots} levels up)"
                
                item = QTreeWidgetItem([imp, resolution])
                item.setForeground(0, QColor("#ce9178"))  # Soft orange
                rel_imports.addChild(item)
            self.imports_tree.addTopLevelItem(rel_imports)
        
        # Invalid imports
        if node_data.get('invalid_imports'):
            invalid_imports = QTreeWidgetItem(["Invalid Imports", "Error"])
            invalid_imports.setForeground(0, QColor("#f48771"))  # Soft red
            for imp in node_data['invalid_imports']:
                error = "Module Not Found" if imp.startswith('.') else "Package Not Found"
                item = QTreeWidgetItem([imp, error])
                item.setForeground(0, QColor("#f48771"))  # Soft red
                invalid_imports.addChild(item)
            self.imports_tree.addTopLevelItem(invalid_imports)
        
        # Expand all items
        self.metrics_tree.expandAll()
        self.imports_tree.expandAll()
        
        # Resize columns to content
        self.metrics_tree.resizeColumnToContents(0)
        self.metrics_tree.resizeColumnToContents(1)
        self.imports_tree.resizeColumnToContents(0)
        self.imports_tree.resizeColumnToContents(1)
    
    def load_file_contents(self, file_path):
        """Load and display file contents with code intelligence."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.code_view.setText(content)
            self.code_view.update_code_intelligence(file_path, content)
        except Exception as e:
            self.code_view.setText(f"Error loading file: {str(e)}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        try:
            # First clear any pending web content
            if self.web_view and self.web_view.page():
                self.web_view.page().setHtml("")
                self.web_view.page().deleteLater()
            
            # Clear the web channel and bridge
            if self.channel:
                if self.bridge:
                    self.channel.deregisterObject(self.bridge)
                self.channel = None
            
            if self.bridge:
                self.bridge.deleteLater()
                self.bridge = None
            
            # Clean up web view
            if self.web_view:
                self.web_view.setParent(None)
                self.web_view.deleteLater()
                self.web_view = None
            
            # Clean up code editor
            if self.code_view:
                self.code_view.setParent(None)
                self.code_view.deleteLater()
                self.code_view = None
            
            # Accept the close event
            event.accept()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            event.accept()  # Still accept the event even if cleanup fails

    async def export_validation_data(self):
        """Export validation data as JSON."""
        if not self.validator:
            QMessageBox.warning(self.window, "Export Data", "No validation data available. Please scan a project first.")
            return
            
        try:
            # Get project path and name
            project_path = Path(self.path_input.text())
            project_name = project_path.name
            
            # Create timestamp and filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"import_validation_{project_name}_{timestamp}.json"
            default_save_path = project_path / default_filename
            
            # Get file path for saving
            file_path, _ = QFileDialog.getSaveFileName(
                self.window,
                "Save Validation Data",
                str(default_save_path),
                "JSON Files (*.json)"
            )
            
            if not file_path:
                return
                
            # Get current validation results
            results = await self.validator.validate_all()
            
            # Convert results to serializable format
            export_data = {
                'project_info': {
                    'base_dir': str(self.validator.base_dir),
                    'src_dir': str(self.validator.src_dir),
                    'tests_dir': str(self.validator.tests_dir) if self.validator.tests_dir else None,
                },
                'imports': {str(k): list(v) for k, v in results.imports.items()},
                'invalid_imports': {str(k): list(v) for k, v in results.invalid_imports.items()},
                'relative_imports': {str(k): list(v) for k, v in results.relative_imports.items()},
                'circular_refs': {str(k): [list(cycle) for cycle in v] for k, v in results.circular_refs.items()},
                'stats': {
                    'total_imports': results.stats.total_imports,
                    'unique_imports': results.stats.unique_imports,
                    'invalid_imports': results.stats.invalid_imports_count,
                    'relative_imports': results.stats.relative_imports_count,
                    'circular_refs': results.stats.circular_refs_count,
                    'complexity_score': results.stats.complexity_score,
                    'stdlib_imports': results.stats.stdlib_imports,
                    'thirdparty_imports': results.stats.thirdparty_imports,
                    'local_imports': results.stats.local_imports
                },
                'package_info': {
                    'installed_packages': list(self.validator.installed_packages),
                    'valid_packages': list(self.validator.config.valid_packages) if hasattr(self.validator.config, 'valid_packages') else [],
                    'requirements': list(self.validator.config.requirements) if hasattr(self.validator.config, 'requirements') else [],
                    'pyproject_dependencies': list(self.validator.config.pyproject_dependencies) if hasattr(self.validator.config, 'pyproject_dependencies') else []
                },
                'file_statuses': {
                    str(path): {
                        'exists': status.exists,
                        'is_test': status.is_test,
                        'import_count': status.import_count,
                        'invalid_imports': status.invalid_imports,
                        'circular_refs': status.circular_refs,
                        'relative_imports': status.relative_imports
                    }
                    for path, status in self.validator.file_statuses.items()
                }
            }
            
            # Save to file with pretty printing
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self.window, "Export Data", f"Validation data exported to:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self.window, "Export Error", f"Failed to export validation data: {str(e)}")
