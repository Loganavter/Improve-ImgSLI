import QtQuick 2.15

Rectangle {
    id: root
    color: canvasBridge.backgroundColor
    clip: true

    function circleLeft(centerX, radius) {
        return Math.round(centerX - radius)
    }

    function circleTop(centerY, radius) {
        return Math.round(centerY - radius)
    }

    Item {
        id: viewport
        anchors.fill: parent
        clip: true

        Item {
            id: contentRect
            x: canvasBridge.contentX
            y: canvasBridge.contentY
            width: canvasBridge.contentWidth
            height: canvasBridge.contentHeight
        }

        Item {
            id: firstSlice
            x: contentRect.x
            y: contentRect.y
            width: canvasBridge.isHorizontal ? contentRect.width : Math.round(contentRect.width * canvasBridge.splitPosition)
            height: canvasBridge.isHorizontal ? Math.round(contentRect.height * canvasBridge.splitPosition) : contentRect.height
            clip: true

            Image {
                x: 0
                y: 0
                width: contentRect.width
                height: contentRect.height
                fillMode: Image.PreserveAspectFit
                smooth: true
                asynchronous: false
                cache: false
                source: canvasBridge.sourceLeft
                transform: [
                    Scale {
                        origin.x: contentRect.width / 2
                        origin.y: contentRect.height / 2
                        xScale: canvasBridge.zoomLevel
                        yScale: canvasBridge.zoomLevel
                    },
                    Translate {
                        x: canvasBridge.panOffsetX * contentRect.width * canvasBridge.zoomLevel
                        y: canvasBridge.panOffsetY * contentRect.height * canvasBridge.zoomLevel
                    }
                ]
            }
        }

        Item {
            id: secondSlice
            x: canvasBridge.isHorizontal ? contentRect.x : contentRect.x + Math.round(contentRect.width * canvasBridge.splitPosition)
            y: canvasBridge.isHorizontal ? contentRect.y + Math.round(contentRect.height * canvasBridge.splitPosition) : contentRect.y
            width: canvasBridge.isHorizontal ? contentRect.width : contentRect.width - (x - contentRect.x)
            height: canvasBridge.isHorizontal ? contentRect.height - (y - contentRect.y) : contentRect.height
            clip: true

            Image {
                x: -(secondSlice.x - contentRect.x)
                y: -(secondSlice.y - contentRect.y)
                width: contentRect.width
                height: contentRect.height
                fillMode: Image.PreserveAspectFit
                smooth: true
                asynchronous: false
                cache: false
                source: canvasBridge.sourceRight
                transform: [
                    Scale {
                        origin.x: contentRect.width / 2
                        origin.y: contentRect.height / 2
                        xScale: canvasBridge.zoomLevel
                        yScale: canvasBridge.zoomLevel
                    },
                    Translate {
                        x: canvasBridge.panOffsetX * contentRect.width * canvasBridge.zoomLevel
                        y: canvasBridge.panOffsetY * contentRect.height * canvasBridge.zoomLevel
                    }
                ]
            }
        }
    }

    Rectangle {
        visible: canvasBridge.showDivider
        color: canvasBridge.dividerColor
        width: canvasBridge.isHorizontal ? contentRect.width : Math.max(1, canvasBridge.dividerThickness)
        height: canvasBridge.isHorizontal ? Math.max(1, canvasBridge.dividerThickness) : contentRect.height
        x: canvasBridge.isHorizontal ? contentRect.x : contentRect.x + Math.round(contentRect.width * canvasBridge.splitPosition) - Math.floor(width / 2)
        y: canvasBridge.isHorizontal ? contentRect.y + Math.round(contentRect.height * canvasBridge.splitPosition) - Math.floor(height / 2) : contentRect.y
        opacity: 0.95
    }

    Repeater {
        model: canvasBridge.overlayCenters

        Item {
            x: 0
            y: 0
            width: root.width
            height: root.height
            z: 11

            Rectangle {
                visible: canvasBridge.guidesVisible && canvasBridge.captureVisible && canvasBridge.captureRadius > 0
                x: Math.min(canvasBridge.captureX, modelData.x)
                y: Math.min(canvasBridge.captureY, modelData.y)
                width: Math.max(1, Math.abs(modelData.x - canvasBridge.captureX))
                height: Math.max(1, Math.abs(modelData.y - canvasBridge.captureY))
                color: "transparent"
                border.width: 0

                Rectangle {
                    anchors.centerIn: parent
                    width: parent.width > parent.height ? parent.width : canvasBridge.guidesThickness
                    height: parent.width > parent.height ? canvasBridge.guidesThickness : parent.height
                    color: canvasBridge.guidesColor
                    rotation: Math.atan2(modelData.y - canvasBridge.captureY, modelData.x - canvasBridge.captureX) * 180 / Math.PI
                }
            }
        }
    }

    Rectangle {
        visible: canvasBridge.captureVisible && canvasBridge.captureRadius > 0
        x: root.circleLeft(canvasBridge.captureX, canvasBridge.captureRadius)
        y: root.circleTop(canvasBridge.captureY, canvasBridge.captureRadius)
        width: canvasBridge.captureRadius * 2
        height: canvasBridge.captureRadius * 2
        radius: canvasBridge.captureRadius
        color: "transparent"
        border.color: canvasBridge.captureColor
        border.width: 2
        z: 12
    }

    Rectangle {
        id: dragOverlay
        visible: canvasBridge.dragOverlayVisible
        anchors.fill: parent
        color: "transparent"
        border.width: 0

        property real overlayMargin: 10
        property real halfMargin: overlayMargin / 2

        Rectangle {
            id: firstDropZone
            x: dragOverlay.overlayMargin
            y: dragOverlay.overlayMargin
            width: canvasBridge.dragOverlayHorizontal
                   ? Math.max(1, dragOverlay.width - dragOverlay.overlayMargin * 2)
                   : Math.max(1, dragOverlay.width / 2 - dragOverlay.overlayMargin - dragOverlay.halfMargin)
            height: canvasBridge.dragOverlayHorizontal
                    ? Math.max(1, dragOverlay.height / 2 - dragOverlay.overlayMargin - dragOverlay.halfMargin)
                    : Math.max(1, dragOverlay.height - dragOverlay.overlayMargin * 2)
            radius: 10
            color: "#990064c8"
            border.color: "#b3ffffff"
            border.width: 1.25

            Text {
                anchors.fill: parent
                anchors.margins: 15
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
                color: "#ffffff"
                font.pixelSize: 20
                font.bold: true
                text: canvasBridge.dragOverlayPrimaryText
            }
        }

        Rectangle {
            id: secondDropZone
            x: canvasBridge.dragOverlayHorizontal
               ? dragOverlay.overlayMargin
               : dragOverlay.width / 2 + dragOverlay.halfMargin
            y: canvasBridge.dragOverlayHorizontal
               ? dragOverlay.height / 2 + dragOverlay.halfMargin
               : dragOverlay.overlayMargin
            width: canvasBridge.dragOverlayHorizontal
                   ? Math.max(1, dragOverlay.width - dragOverlay.overlayMargin * 2)
                   : Math.max(1, dragOverlay.width / 2 - dragOverlay.overlayMargin - dragOverlay.halfMargin)
            height: canvasBridge.dragOverlayHorizontal
                    ? Math.max(1, dragOverlay.height / 2 - dragOverlay.overlayMargin - dragOverlay.halfMargin)
                    : Math.max(1, dragOverlay.height - dragOverlay.overlayMargin * 2)
            radius: 10
            color: "#990064c8"
            border.color: "#b3ffffff"
            border.width: 1.25

            Text {
                anchors.fill: parent
                anchors.margins: 15
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.Wrap
                color: "#ffffff"
                font.pixelSize: 20
                font.bold: true
                text: canvasBridge.dragOverlaySecondaryText
            }
        }
    }

    Image {
        id: magnifierOverlay
        visible: canvasBridge.magnifierVisible && canvasBridge.magnifierSource.length > 0
        x: canvasBridge.magnifierX
        y: canvasBridge.magnifierY
        z: 10
        smooth: true
        asynchronous: false
        cache: false
        source: canvasBridge.magnifierSource
    }
}
