

from OpenGL import GL as gl
from PyQt6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)

from .geometry import OVERLAY_QUAD
from .shaders import (
    MAGNIFIER_GPU_FRAGMENT,
    MAGNIFIER_SCREEN_VERTEX,
    MAGNIFIER_TEXTURE_FRAGMENT,
)

class MagnifierPass:

    def __init__(self):
        self.program_texture: QOpenGLShaderProgram | None = None
        self.program_gpu: QOpenGLShaderProgram | None = None
        self.vao: QOpenGLVertexArrayObject | None = None
        self.vbo: QOpenGLBuffer | None = None

    def init_gl(self):
        self.program_texture = QOpenGLShaderProgram()
        self.program_texture.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, MAGNIFIER_SCREEN_VERTEX
        )
        self.program_texture.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, MAGNIFIER_TEXTURE_FRAGMENT
        )
        self.program_texture.link()

        self.program_gpu = QOpenGLShaderProgram()
        self.program_gpu.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, MAGNIFIER_SCREEN_VERTEX
        )
        self.program_gpu.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, MAGNIFIER_GPU_FRAGMENT
        )
        self.program_gpu.link()

        self.vao = QOpenGLVertexArrayObject()
        self.vao.create()
        self.vao.bind()
        self.vbo = QOpenGLBuffer()
        self.vbo.create()
        self.vbo.bind()
        self.vbo.allocate(OVERLAY_QUAD.tobytes(), OVERLAY_QUAD.nbytes)
        for prog in (self.program_texture, self.program_gpu):
            prog.enableAttributeArray(0)
            prog.setAttributeBuffer(0, gl.GL_FLOAT, 0, 2, 4 * 4)
            prog.enableAttributeArray(1)
            prog.setAttributeBuffer(1, gl.GL_FLOAT, 2 * 4, 2, 4 * 4)
        self.vbo.release()
        self.vao.release()

    def draw_textured(
        self,
        viewport_w: float,
        viewport_h: float,
        left: float,
        top: float,
        width: float,
        height: float,
        texture_id: int,
    ):
        """Рисует лупу из одной текстуры (экранный квад)."""
        if not self.program_texture or not self.program_texture.isLinked() or width <= 0 or height <= 0:
            return
        self.program_texture.bind()
        self.program_texture.setUniformValue("offset", left, top)
        self.program_texture.setUniformValue("size", width, height)
        self.program_texture.setUniformValue("viewport", viewport_w, viewport_h)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
        self.program_texture.setUniformValue("tex", 0)
        self.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        self.vao.release()
        self.program_texture.release()

    def draw_gpu(
        self,
        viewport_w: float,
        viewport_h: float,
        bbox_x: float,
        bbox_y: float,
        bbox_w: float,
        bbox_h: float,
        uv_rect1: tuple,
        uv_rect2: tuple,
        internal_split: float,
        is_horizontal: bool,
        texture_id_0: int,
        texture_id_1: int,
    ):
        """Рисует лупу сэмплированием из двух основных текстур."""
        if not self.program_gpu or not self.program_gpu.isLinked() or bbox_w <= 0 or bbox_h <= 0:
            return
        self.program_gpu.bind()
        self.program_gpu.setUniformValue("offset", bbox_x, bbox_y)
        self.program_gpu.setUniformValue("size", bbox_w, bbox_h)
        self.program_gpu.setUniformValue("viewport", viewport_w, viewport_h)
        self.program_gpu.setUniformValue("splitPos", internal_split)
        self.program_gpu.setUniformValue("isHorizontal", is_horizontal)
        self.program_gpu.setUniformValue("uvRect1", *uv_rect1)
        self.program_gpu.setUniformValue("uvRect2", *uv_rect2)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id_0)
        self.program_gpu.setUniformValue("image1", 0)
        gl.glActiveTexture(gl.GL_TEXTURE1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id_1)
        self.program_gpu.setUniformValue("image2", 1)
        self.vao.bind()
        gl.glDrawArrays(gl.GL_TRIANGLE_STRIP, 0, 4)
        self.vao.release()
        self.program_gpu.release()
