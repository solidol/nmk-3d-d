import adsk.core
import adsk.fusion
import math
import traceback


APP = adsk.core.Application.get()
UI = APP.userInterface


def point(x_mm, y_mm):
    """Create a sketch point. Fusion API internal length unit is centimetres."""
    return adsk.core.Point3D.create(x_mm / 10.0, y_mm / 10.0, 0)


def add_closed_profile(sketch, points_mm):
    lines = sketch.sketchCurves.sketchLines
    for index, start in enumerate(points_mm):
        end = points_mm[(index + 1) % len(points_mm)]
        lines.addByTwoPoints(point(*start), point(*end))


def create_bell(component):
    sketch = component.sketches.add(component.xZConstructionPlane)
    sketch.name = 'Профіль дзвона'

    # Keep the axis separate from the profile boundary. Turning a boundary
    # line into construction geometry would open the contour and remove the
    # profile required by Revolve.
    axis = sketch.sketchCurves.sketchLines.addByTwoPoints(
        point(0, 0), point(0, -44)
    )
    axis.isConstruction = True

    # Half-profile in millimetres: axis, base rim, curved-looking stepped body,
    # shoulder and neck. Straight short segments keep the example robust.
    profile_points_upright = [
        (0, 0),
        (15, 0),
        (15, 4),
        (13.5, 6),
        (12.5, 10),
        (11.5, 16),
        (10.5, 24),
        (9.5, 32),
        (8.0, 37),
        (6.5, 40),
        (6.0, 44),
        (0, 44),
    ]
    # Negative sketch Y places the narrow neck above the wide bell mouth in
    # Fusion's standard front view.
    profile_points = [(x, -y) for x, y in profile_points_upright]
    add_closed_profile(sketch, profile_points)

    if sketch.profiles.count == 0:
        raise RuntimeError('Не створено замкненого профілю дзвона.')

    revolves = component.features.revolveFeatures
    revolve_input = revolves.createInput(
        sketch.profiles.item(0),
        axis,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    revolve_input.setAngleExtent(
        False, adsk.core.ValueInput.createByReal(2 * math.pi)
    )
    feature = revolves.add(revolve_input)
    feature.name = 'Корпус дзвона — Revolve 360°'
    feature.bodies.item(0).name = 'Дзвін з рельєфним написом'
    return feature.bodies.item(0)


def create_text_sketch(component, label):
    # Place the sketch outside the largest bell diameter. Emboss projects the
    # text from this plane onto the selected curved faces.
    planes = component.constructionPlanes
    plane_input = planes.createInput()
    plane_input.setByOffset(
        component.xZConstructionPlane,
        adsk.core.ValueInput.createByString('-16 mm'),
    )
    text_plane = planes.add(plane_input)
    text_plane.name = 'Дотична площина для напису'

    sketch = component.sketches.add(text_plane)
    sketch.name = 'Напис на поверхні'
    texts = sketch.sketchTexts

    # Scale longer labels so they remain inside the useful 18 mm-wide belt.
    # The lower limit keeps the result printable and readable.
    text_height_mm = max(1.5, min(4.0, 16.0 / (0.65 * len(label))))
    path_width_mm = 18.0

    # createInput3 is current from Fusion November 2025. The fallback keeps
    # the script usable in older educational installations.
    try:
        text_input = texts.createInput3(
            "'" + label.replace("'", "\\'") + "'",
            adsk.core.ValueInput.createByString(f'{text_height_mm:.2f} mm'),
        )
    except Exception:
        text_input = texts.createInput2(label, text_height_mm / 10.0)

    text_path = sketch.sketchCurves.sketchLines.addByTwoPoints(
        point(-path_width_mm / 2.0, -24),
        point(path_width_mm / 2.0, -24),
    )
    text_path.isConstruction = True
    text_input.setAsAlongPath(
        text_path,
        True,
        adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
        0,
    )
    # The offset XZ sketch is projected from its back side onto the visible
    # bell surface, so compensate for the resulting horizontal mirror.
    text_input.isHorizontalFlip = True
    sketch_text = texts.add(text_input)
    return sketch, sketch_text


def emboss_text(component, body, sketch_text):
    target_faces = []
    for face in body.faces:
        is_curved = not isinstance(face.geometry, adsk.core.Plane)
        if is_curved:
            target_faces.append(face)

    if not target_faces:
        raise RuntimeError(
            'Не знайдено криволінійних граней корпуса дзвона.'
        )

    try:
        embosses = component.features.embossFeatures
    except Exception as error:
        raise RuntimeError(
            'У цій версії Fusion API немає EmbossFeatures. '
            'Оновіть Fusion до версії за вересень 2025 року або новішої.'
        ) from error

    emboss_input = embosses.createInput(
        [sketch_text],
        target_faces,
        adsk.core.ValueInput.createByString('0.6 mm'),
    )
    emboss_input.isTangentChain = True
    feature = embosses.add(emboss_input)
    if not feature:
        raise RuntimeError(
            'Операцію Emboss не створено. Спробуйте коротший напис.'
        )
    feature.name = 'Викривлений напис — Emboss 0,6 мм'


def run(context):
    try:
        result = UI.inputBox(
            'Введіть напис для дзвона (1–20 символів).',
            'Навчальний дзвін із написом',
            '3D',
        )
        if result[1]:
            return
        label = result[0].strip() or '3D'
        if len(label) > 20:
            UI.messageBox('Напис скорочено до перших 20 символів.')
            label = label[:20]

        document = APP.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(APP.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        component = design.rootComponent

        body = create_bell(component)
        text_sketch, sketch_text = create_text_sketch(component, label)
        emboss_text(component, body, sketch_text)

        APP.activeViewport.fit()
        UI.messageBox(
            'Готово: створено дзвін Revolve 360° із викривленим '
            f'написом «{label}».\n\n'
            'Збережіть модель під новим ім’ям.'
        )
    except Exception:
        UI.messageBox(
            'Не вдалося створити модель:\n\n' + traceback.format_exc()
        )


def stop(context):
    pass
