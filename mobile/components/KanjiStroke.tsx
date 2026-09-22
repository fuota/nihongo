import { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Line, Path, Text as SvgText } from 'react-native-svg';

type Props = {
  strokePaths: string[];
  size?: number;
  strokeMs?: number;
};

type Geometry = {
  // the exact strokePaths array this geometry was measured for -- render
  // logic checks this by reference before trusting geometry at all, see
  // note below on why that matters
  forPaths: string[];
  items: { length: number; labelPos: { x: number; y: number } }[];
};

const AnimatedPath = Animated.createAnimatedComponent(Path);

/**
 * Plays back a kanji's strokes one at a time (KanjiVG data, viewBox is
 * always 0 0 109 109), animating each stroke drawing from its start
 * point to its end point via the classic SVG strokeDasharray/
 * strokeDashoffset trick, and numbering each stroke as it appears.
 *
 * Path lengths and start points are measured natively via getTotalLength/
 * getPointAtLength once the underlying native views exist.
 *
 * Geometry is tagged with the exact strokePaths array it was measured
 * for (`forPaths`), and render only trusts it when that matches the
 * current props by reference. Without this, the render that immediately
 * follows a strokePaths change would use the NEW paths' `d` values
 * together with the OLD geometry/dashOffsets (state updates queued in
 * an effect don't apply until the next render) -- for a character with
 * more strokes than the previous one, that means indexing into geometry
 * past its length, and calling getTotalLength on native views that
 * haven't stabilized for the new data yet, which crashes native-side
 * ("Invalid svg returned from registry ... got: (null)"). Falling back
 * to the plain invisible-placeholder rendering whenever geometry is
 * stale keeps every transition on a clean, uniform native tree before
 * measurement is attempted again.
 *
 * Each stroke gets its own Animated.Value for strokeDashoffset, created
 * once geometry is measured and never swapped out for a plain number --
 * driving a stroke's dashoffset with an Animated interpolation while
 * it's being drawn, then replacing that prop with a static 0 once
 * "done", made already-drawn strokes flicker invisible (Animated's
 * prop-diffing doesn't cleanly detach from a value it was previously
 * bound to). Keeping every stroke on its own stable Animated.Value for
 * its entire lifecycle -- hidden, animating, then resting at 0 -- avoids
 * that entirely.
 */
export function KanjiStroke({ strokePaths, size = 220, strokeMs = 450 }: Props) {
  const [geometryState, setGeometryState] = useState<Geometry | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const pathRefs = useRef<(Path | null)[]>([]);
  const dashOffsets = useRef<Animated.Value[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A fresh inline arrow function passed as `ref` has a new identity every
  // render, and React treats that as the ref itself changing -- it calls
  // the old ref with null then the new one with the instance, on EVERY
  // render, not just mount/unmount. That was intermittently nulling out
  // pathRefs entries right as measure() (or the native getTotalLength
  // call it triggers) tried to read them. Caching one stable callback per
  // index keeps the same function identity across renders, so React only
  // attaches/detaches when a Path element actually mounts or unmounts.
  const refCallbacks = useRef<((r: Path | null) => void)[]>([]);
  const getPathRef = (i: number) => {
    if (!refCallbacks.current[i]) {
      refCallbacks.current[i] = (r: Path | null) => {
        pathRefs.current[i] = r;
      };
    }
    return refCallbacks.current[i];
  };

  const geometry = geometryState?.forPaths === strokePaths ? geometryState.items : null;

  // Returns whether geometry for the CURRENT strokePaths is in place after
  // this call (whether it already was, or just got set) -- callers that
  // retry on a timer use this return value, not geometryState, to decide
  // whether to keep going: geometryState is a stale closure value inside
  // a retry loop started by an effect, so it would never reflect this
  // function's own setGeometryState calls between retries.
  const measure = (): boolean => {
    if (geometryState?.forPaths === strokePaths) return true; // already measured for this data
    // getTotalLength/getPointAtLength can crash native-side ("Invalid svg
    // returned from registry ... got: (null)") if called before a Path's
    // RNSVGRenderable has fully finished registering -- the Svg
    // container's onLayout firing doesn't guarantee every child Path has
    // too. There's no completion event to wait on, so this is caught
    // (treated the same as "not ready yet") rather than left to crash.
    let items: { length: number; labelPos: { x: number; y: number } }[];
    try {
      items = strokePaths.map((_, i) => {
        const ref = pathRefs.current[i];
        const length = ref?.getTotalLength?.() ?? 0;
        if (length === 0) return { length, labelPos: { x: 0, y: 0 } };
        // Position the stroke number just before its start point, offset
        // to the side of the direction the stroke actually travels in --
        // a fixed offset (e.g. always up-and-left) looks fine for most
        // strokes but lands squarely on top of the ink for others,
        // wherever that fixed direction happens to match the stroke's
        // own path (reported: stroke 2 of 夕). Sampling a point a little
        // further along the path gives the initial travel direction, and
        // offsetting perpendicular to it (rotated -90°) plus a bit
        // backward keeps the number consistently just outside the ink
        // regardless of which way a given stroke happens to go.
        const start = ref!.getPointAtLength(0);
        const ahead = ref!.getPointAtLength(Math.min(4, length * 0.4));
        const dx = ahead.x - start.x;
        const dy = ahead.y - start.y;
        const dist = Math.hypot(dx, dy) || 1;
        const tx = dx / dist;
        const ty = dy / dist;
        const px = -ty;
        const py = tx;
        const SIDE = 4;
        const BACK = 2.5;
        const labelPos = { x: start.x + px * SIDE - tx * BACK, y: start.y + py * SIDE - ty * BACK };
        return { length, labelPos };
      });
    } catch {
      return false; // native views not ready yet -- retry will catch it
    }
    if (items.some((it) => it.length === 0)) return false; // native views not ready yet
    dashOffsets.current = items.map((it) => new Animated.Value(it.length));
    setGeometryState({ forPaths: strokePaths, items });
    return true;
  };

  useEffect(() => {
    setActiveIndex(-1);
    // NOTE: do not reset pathRefs.current here. Ref attachment for the
    // just-committed render (with the new strokePaths) already happened
    // before this effect runs -- clearing the array now would throw away
    // the refs that were just correctly populated, and every measure()
    // call would see nothing but empty slots.
    //
    // measure() can quietly no-op (native views not ready, or the
    // getTotalLength race caught above) with nothing guaranteed to call
    // it again -- onLayout only refires on an actual layout change, which
    // may never happen once the Svg's fixed size is already laid out. So
    // this retries on a short interval until geometry for this exact
    // strokePaths array is in place, capped well past any plausible
    // native init delay.
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tryMeasure = () => {
      const done = measure();
      attempts += 1;
      if (!done && attempts < 20) {
        timer = setTimeout(tryMeasure, 100);
      }
    };
    const raf = requestAnimationFrame(tryMeasure);
    return () => {
      cancelAnimationFrame(raf);
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strokePaths]);

  const play = () => {
    if (!geometry) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    dashOffsets.current.forEach((value, i) => {
      value.stopAnimation();
      value.setValue(geometry[i].length);
    });
    setActiveIndex(-1);

    const step = (i: number) => {
      if (i >= strokePaths.length) return;
      setActiveIndex(i);
      Animated.timing(dashOffsets.current[i], {
        toValue: 0,
        duration: strokeMs,
        useNativeDriver: false, // strokeDashoffset isn't supported by the native driver
      }).start(() => {
        timerRef.current = setTimeout(() => step(i + 1), 150);
      });
    };
    step(0);
  };

  useEffect(() => {
    if (geometry) play();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      dashOffsets.current.forEach((value) => value.stopAnimation());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry]);

  return (
    <View style={styles.container}>
      <Svg width={size} height={size} viewBox="0 0 109 109" onLayout={measure}>
        <Path d="M2,2 L107,2 L107,107 L2,107 Z" stroke="#e0e0e0" strokeWidth={1} fill="none" />
        <Line x1="54.5" y1="2" x2="54.5" y2="107" stroke="#ccc" strokeWidth={1} strokeDasharray="4,4" />
        <Line x1="2" y1="54.5" x2="107" y2="54.5" stroke="#ccc" strokeWidth={1} strokeDasharray="4,4" />

        {strokePaths.map((d, i) => {
          if (!geometry) {
            // not measured yet -- render invisibly so the ref still
            // attaches and getTotalLength/getPointAtLength work
            return (
              <Path
                key={i}
                ref={getPathRef(i)}
                d={d}
                stroke="transparent"
                strokeWidth={3}
                fill="none"
              />
            );
          }

          return (
            <AnimatedPath
              key={i}
              ref={getPathRef(i)}
              d={d}
              stroke="#000"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
              strokeDasharray={geometry[i].length}
              strokeDashoffset={dashOffsets.current[i]}
            />
          );
        })}

        {geometry &&
          strokePaths.map((_, i) =>
            i <= activeIndex ? (
              <SvgText
                key={i}
                x={geometry[i].labelPos.x}
                y={geometry[i].labelPos.y}
                fontSize={5.5}
                fill="#000"
                textAnchor="middle">
                {i + 1}
              </SvgText>
            ) : null
          )}
      </Svg>
      <Pressable style={styles.replayButton} onPress={play}>
        <Text style={styles.replayText}>↻ Replay</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    gap: 8,
  },
  replayButton: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 8,
    backgroundColor: '#f0f0f0',
  },
  replayText: {
    fontSize: 13,
    color: '#444',
  },
});
