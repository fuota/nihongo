import {
  Canvas,
  DashPathEffect,
  Group,
  matchFont,
  Path,
  Skia,
  SkPath,
  Text as SkiaText,
  useCanvasRef,
} from '@shopify/react-native-skia';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';

// Position for a stroke's number label: just before its start point,
// offset to the side of the direction the stroke actually travels in.
// A fixed offset (e.g. always up-and-left) looks fine for most strokes
// but lands squarely on top of the ink for others, wherever that fixed
// direction happens to match the stroke's own path (reported: stroke 2
// of 夕). Skia's contour measurer gives the real tangent direction at
// the start of the path, so offsetting perpendicular to it (rotated
// -90°) plus a bit backward keeps the number consistently just outside
// the ink regardless of which way a given stroke happens to go -- same
// approach as KanjiStroke's playback numbering.
function getHintLabelPos(path: SkPath): { x: number; y: number } | null {
  const contour = Skia.ContourMeasureIter(path, false, 1).next();
  if (!contour) return null;
  const [start, tan] = contour.getPosTan(0);
  const px = -tan.y;
  const py = tan.x;
  const SIDE = 4;
  const BACK = 2.5;
  return { x: start.x + px * SIDE - tan.x * BACK, y: start.y + py * SIDE - tan.y * BACK };
}

type Props = {
  size?: number;
  onSubmit: (base64Png: string) => void;
  submitting?: boolean;
  showControls?: boolean;
  // KanjiVG stroke path "d" strings (0-109 viewBox, same data KanjiStroke
  // uses) to trace over as a faint hint, toggled via the lightbulb button.
  hintPaths?: string[];
};

// KanjiVG data is always defined in a fixed 109x109 viewBox.
const HINT_VIEWBOX_SIZE = 109;

/**
 * @shopify/react-native-skia v2 dropped its old useTouchHandler/onTouch
 * API, and its native Canvas view does not forward touches through
 * React Native's plain touch responder system either (confirmed
 * empirically -- onTouchStart on Canvas itself, and on a plain wrapping
 * View, both silently never fired, on both Simulator and a physical
 * device). react-native-gesture-handler is the integration path Skia
 * v2 actually expects. runOnJS(true) keeps the callbacks as plain JS
 * functions (not Reanimated worklets), so this stays the same
 * imperative Skia.Path mutation + setState pattern as a normal touch
 * handler would use.
 */
export function DrawingCanvas({
  size = 300,
  onSubmit,
  submitting = false,
  showControls = true,
  hintPaths,
}: Props) {
  const canvasRef = useCanvasRef();
  const currentPath = useRef<SkPath | null>(null);
  const [paths, setPaths] = useState<SkPath[]>([]);
  const [showHint, setShowHint] = useState(false);

  const hintStrokes = useMemo(() => {
    if (!hintPaths) return [];
    return hintPaths
      .map((d) => {
        const path = Skia.Path.MakeFromSVGString(d);
        if (!path) return null;
        return { path, labelPos: getHintLabelPos(path) };
      })
      .filter((s): s is { path: SkPath; labelPos: { x: number; y: number } | null } => s !== null);
  }, [hintPaths]);
  const hasHint = hintStrokes.length > 0;
  // computed inside the component (not at module scope) so it only runs
  // once Skia's native module is definitely initialized. "System" is a
  // React Native/CSS alias (mapped to San Francisco by RN's own text
  // renderer) -- Skia's matchFont goes straight to the platform font
  // manager (CoreText on iOS) and doesn't know that alias, so it must be
  // given a real font family name instead.
  const hintNumberFont = useMemo(
    () => matchFont({ fontFamily: 'Helvetica', fontSize: 5.5, fontWeight: 'bold' }),
    []
  );

  const onStart = (x: number, y: number) => {
    const path = Skia.Path.Make();
    path.moveTo(x, y);
    currentPath.current = path;
    setPaths((prev) => [...prev, path]);
  };

  const onUpdate = (x: number, y: number) => {
    currentPath.current?.lineTo(x, y);
    setPaths((prev) => [...prev]);
  };

  const onFinish = () => {
    currentPath.current = null;
  };

  const pan = Gesture.Pan()
    .runOnJS(true)
    .onStart((e) => onStart(e.x, e.y))
    .onUpdate((e) => onUpdate(e.x, e.y))
    .onEnd(onFinish)
    .minDistance(0);

  const clear = () => setPaths([]);

  const submit = () => {
    const image = canvasRef.current?.makeImageSnapshot();
    if (!image) return;
    const base64 = image.encodeToBase64();
    onSubmit(base64);
  };

  const gridPath = Skia.Path.Make();
  gridPath.moveTo(size / 2, 0);
  gridPath.lineTo(size / 2, size);
  gridPath.moveTo(0, size / 2);
  gridPath.lineTo(size, size / 2);

  return (
    <View style={styles.container}>
      <View style={{ width: size, height: size }}>
        <GestureDetector gesture={pan}>
          <View style={[styles.canvasWrap, { width: size, height: size }]}>
            <Canvas ref={canvasRef} style={{ flex: 1 }}>
              <Path path={Skia.Path.Make().addRect(Skia.XYWHRect(0, 0, size, size))} color="white" />
              {showHint && hasHint && (
                <Group transform={[{ scale: size / HINT_VIEWBOX_SIZE }]}>
                  {hintStrokes.map(({ path }, i) => (
                    <Path
                      key={i}
                      path={path}
                      color="#ccc"
                      style="stroke"
                      strokeWidth={3}
                      strokeCap="round"
                      strokeJoin="round"
                    />
                  ))}
                  {hintNumberFont &&
                    hintStrokes.map(({ labelPos }, i) =>
                      labelPos ? (
                        <SkiaText
                          key={i}
                          x={labelPos.x}
                          y={labelPos.y}
                          text={String(i + 1)}
                          font={hintNumberFont}
                          color="#ccc"
                        />
                      ) : null
                    )}
                </Group>
              )}
              <Path path={gridPath} color="#ccc" style="stroke" strokeWidth={1}>
                <DashPathEffect intervals={[6, 6]} />
              </Path>
              {paths.map((path, i) => (
                <Path
                  key={i}
                  path={path}
                  color="black"
                  style="stroke"
                  strokeWidth={10}
                  strokeCap="round"
                  strokeJoin="round"
                />
              ))}
            </Canvas>
          </View>
        </GestureDetector>

        {hasHint && (
          <Pressable style={styles.hintButton} onPress={() => setShowHint((v) => !v)} hitSlop={8}>
            <MaterialIcons
              name={showHint ? 'lightbulb' : 'lightbulb-outline'}
              size={20}
              color={showHint ? '#e2a71d' : '#999'}
            />
          </Pressable>
        )}
      </View>

      {showControls && (
        <View style={styles.buttonRow}>
          <Pressable style={[styles.button, styles.clearButton]} onPress={clear} disabled={submitting}>
            <Text style={styles.clearButtonText}>Clear</Text>
          </Pressable>
          <Pressable
            style={[styles.button, styles.submitButton]}
            onPress={submit}
            disabled={submitting || paths.length === 0}>
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.submitButtonText}>Check</Text>
            )}
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: 16,
  },
  hintButton: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.85)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#eee',
  },
  canvasWrap: {
    borderWidth: 2,
    borderColor: '#ddd',
    borderRadius: 12,
    overflow: 'hidden',
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
  },
  button: {
    paddingVertical: 12,
    paddingHorizontal: 28,
    borderRadius: 8,
  },
  clearButton: {
    backgroundColor: '#f0f0f0',
  },
  clearButtonText: {
    color: '#444',
    fontFamily: 'Poppins_600SemiBold',
  },
  submitButton: {
    backgroundColor: '#000',
  },
  submitButtonText: {
    color: '#fff',
    fontFamily: 'Poppins_600SemiBold',
  },
});
