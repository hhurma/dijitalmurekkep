def add_drawing_tools(self, toolbar):
    """Çizim araçlarını toolbar'a ekler."""
    
    # --- Kalem Aracı --- #
    self.pen_button = QToolButton(self)
    self.pen_button.setIcon(QIcon("icons/pen_icon.png"))
    self.pen_button.setToolTip("Kalem Aracı")
    self.pen_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.PEN))
    toolbar.addWidget(self.pen_button)
    
    # --- Çizgi Aracı --- #
    self.line_button = QToolButton(self)
    self.line_button.setIcon(QIcon("icons/line_icon.png"))
    self.line_button.setToolTip("Çizgi Aracı")
    self.line_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.LINE))
    toolbar.addWidget(self.line_button)
    
    # --- Dikdörtgen Aracı --- #
    self.rect_button = QToolButton(self)
    self.rect_button.setIcon(QIcon("icons/rectangle_icon.png"))
    self.rect_button.setToolTip("Dikdörtgen Aracı")
    self.rect_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.RECTANGLE))
    toolbar.addWidget(self.rect_button)
    
    # --- Daire Aracı --- #
    self.circle_button = QToolButton(self)
    self.circle_button.setIcon(QIcon("icons/circle_icon.png"))
    self.circle_button.setToolTip("Daire Aracı")
    self.circle_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.CIRCLE))
    toolbar.addWidget(self.circle_button)
    
    # --- Silgi Aracı --- #
    self.eraser_button = QToolButton(self)
    self.eraser_button.setIcon(QIcon("icons/eraser_icon.png"))
    self.eraser_button.setToolTip("Silgi Aracı")
    self.eraser_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.ERASER))
    toolbar.addWidget(self.eraser_button)
    
    # --- Seçim Aracı --- #
    self.select_button = QToolButton(self)
    self.select_button.setIcon(QIcon("icons/selection_icon.png"))
    self.select_button.setToolTip("Seçim Aracı")
    self.select_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.SELECTOR))
    toolbar.addWidget(self.select_button)
    
    # --- Geçici Lazer İşaretçi Aracı --- #
    self.laser_button = QToolButton(self)
    self.laser_button.setIcon(QIcon("icons/laser_pointer_icon.png"))
    self.laser_button.setToolTip("Lazer İşaretçi")
    self.laser_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.LASER_POINTER))
    toolbar.addWidget(self.laser_button)
    
    # --- Geçici İşaretçi / Çizgi Aracı --- #
    self.temp_pointer_button = QToolButton(self)
    self.temp_pointer_button.setIcon(QIcon("icons/temp_pointer_icon.png"))
    self.temp_pointer_button.setToolTip("Geçici İşaretçi (15sn)")
    self.temp_pointer_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.TEMPORARY_POINTER))
    toolbar.addWidget(self.temp_pointer_button)
    
    # --- YENİ: Düzenlenebilir Çizgi Aracı --- #
    self.editable_line_button = QToolButton(self)
    self.editable_line_button.setIcon(QIcon("icons/editable_line_icon.png"))
    self.editable_line_button.setToolTip("Düzenlenebilir Çizgi")
    self.editable_line_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.EDITABLE_LINE))
    toolbar.addWidget(self.editable_line_button)
    
    # --- YENİ: Düzenlenebilir Çizgi Düzenleme Aracı --- #
    self.editable_line_editor_button = QToolButton(self)
    self.editable_line_editor_button.setIcon(QIcon("icons/editable_line_editor_icon.png"))
    self.editable_line_editor_button.setToolTip("Düzenlenebilir Çizgi Düzenleyici")
    self.editable_line_editor_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.EDITABLE_LINE_EDITOR))
    toolbar.addWidget(self.editable_line_editor_button)
    
    # --- YENİ: Düzenlenebilir Çizgi Kontrol Noktası Seçici --- #
    self.node_selector_button = QToolButton(self)
    self.node_selector_button.setIcon(qta.icon('fa5s.bezier-curve'))
    self.node_selector_button.setToolTip("Kontrol Noktası Seçici")
    self.node_selector_button.clicked.connect(lambda: self.set_drawing_tool(ToolType.EDITABLE_LINE_NODE_SELECTOR))
    toolbar.addWidget(self.node_selector_button)
    
    # --- Ayırıcı --- #
    toolbar.addSeparator() 