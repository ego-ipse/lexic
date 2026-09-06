// A long-lived JVM that parses one framed input per request and reports the
// nanoseconds the parse itself took.
//
// The one methodology that has held up here is interleaved in-process A/B:
// every engine takes a turn each round, so machine load moves all columns
// together. A cross-process ANTLR row would break that — so the JVM stays alive
// for the whole run, Python drives the alternation, and the number crossing the
// pipe is measured by System.nanoTime() INSIDE the JVM, around the parse only.
// Pipe framing, UTF-8 decoding and JVM startup are therefore in no number.
//
// Frame in:  <decimal byte length>\n<utf-8 bytes>   (length -1 quits)
// Frame out: OK <parse ns> <charstream ns>   |   ERR <message>

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.io.PrintStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;

import org.antlr.v4.runtime.BailErrorStrategy;
import org.antlr.v4.runtime.BaseErrorListener;
import org.antlr.v4.runtime.CharStream;
import org.antlr.v4.runtime.CharStreams;
import org.antlr.v4.runtime.CommonTokenStream;
import org.antlr.v4.runtime.DefaultErrorStrategy;
import org.antlr.v4.runtime.Lexer;
import org.antlr.v4.runtime.Parser;
import org.antlr.v4.runtime.RecognitionException;
import org.antlr.v4.runtime.Recognizer;
import org.antlr.v4.runtime.TokenStream;
import org.antlr.v4.runtime.atn.PredictionMode;
import org.antlr.v4.runtime.misc.ParseCancellationException;

public final class Driver {

    /** Turn ANTLR's recover-and-continue default into a refusal.
     *
     * A parser left on its defaults reports a syntax error and carries on with a
     * repaired parse, so it accepts almost anything — it would pass the accept
     * half of the differential while describing a different language. The Python
     * runtime's row gets the same treatment; an asymmetry here would be one
     * engine being allowed not to answer the question. */
    private static final class Strict extends BaseErrorListener {
        @Override
        public void syntaxError(Recognizer<?, ?> recognizer, Object symbol, int line,
                                int column, String message, RecognitionException e) {
            throw new IllegalStateException(line + ":" + column + " " + message);
        }
    }

    private final Lexer lexer;
    private final CommonTokenStream tokens;
    private final Parser parser;
    private final Method entry;
    private final Strict strict = new Strict();

    private Driver(String name) throws Exception {
        Class<?> lexerClass = Class.forName(name + "Lexer");
        Class<?> parserClass = Class.forName(name + "Parser");
        Constructor<?> lexerCtor = lexerClass.getConstructor(CharStream.class);
        Constructor<?> parserCtor = parserClass.getConstructor(TokenStream.class);
        this.lexer = (Lexer) lexerCtor.newInstance(CharStreams.fromString(""));
        this.tokens = new CommonTokenStream(this.lexer);
        this.parser = (Parser) parserCtor.newInstance(this.tokens);
        this.entry = parserClass.getMethod("entry_");
        this.lexer.removeErrorListeners();
        this.lexer.addErrorListener(strict);
        this.parser.removeErrorListeners();
        this.parser.addErrorListener(strict);
    }

    /** Parse {@code text} whole, returning {@code {parse ns, charstream ns}}.
     *
     * The lexer and parser are built once and re-fed, which is how ANTLR is
     * meant to be driven repeatedly. Building the CharStream IS timed: it is
     * per-input work every other engine also pays when handed a string, and the
     * second figure says how much of the number it accounts for. */
    private long[] round(String text) throws Exception {
        long start = System.nanoTime();
        CharStream stream = CharStreams.fromString(text);
        long built = System.nanoTime();
        feed(stream);
        twoStage(stream);
        return new long[] {System.nanoTime() - start, built - start};
    }

    /** Point the lexer, token stream and parser at {@code stream} from its start. */
    private void feed(CharStream stream) {
        lexer.setInputStream(stream);
        tokens.setTokenSource(lexer);
        parser.setTokenStream(tokens);
    }

    /** SLL with a bail strategy first; full LL only when that stage gives up.
     *
     * ANTLR's own documented fast configuration: SLL decides almost every input
     * on its own, and the inputs it cannot decide are re-parsed under the exact
     * configuration the one-stage seat used — same prediction mode, same error
     * strategy, same listener — so what the seat ACCEPTS and what it REFUSES are
     * unchanged, message included.
     *
     * The rewind is the load-bearing line. Stage one leaves the CharStream
     * wherever it stopped, and `Lexer.setInputStream` nulls the lexer's input
     * before resetting it, so nothing puts the stream back to the beginning:
     * without the seek, stage two re-lexes the TAIL and answers a question about
     * a different input. It fails in the accepting direction — a suffix that
     * happens to parse turns a refusal into an acceptance — which is why the
     * differential, not a crash, is what catches it. */
    private void twoStage(CharStream stream) throws Exception {
        parser.getInterpreter().setPredictionMode(PredictionMode.SLL);
        parser.removeErrorListeners();
        parser.setErrorHandler(new BailErrorStrategy());
        try {
            entry.invoke(parser);
            return;
        } catch (InvocationTargetException e) {
            if (!(e.getCause() instanceof ParseCancellationException)) {
                throw e;
            }
        } finally {
            parser.getInterpreter().setPredictionMode(PredictionMode.LL);
            parser.setErrorHandler(new DefaultErrorStrategy());
            parser.addErrorListener(strict);
        }
        stream.seek(0);
        feed(stream);
        entry.invoke(parser);
    }

    /** Read one length-prefixed frame, or {@code null} at the quit signal. */
    private static byte[] frame(DataInputStream in) throws Exception {
        StringBuilder header = new StringBuilder();
        for (int c = in.read(); c != '\n'; c = in.read()) {
            if (c < 0) {
                return null;
            }
            header.append((char) c);
        }
        int length = Integer.parseInt(header.toString().trim());
        if (length < 0) {
            return null;
        }
        byte[] body = new byte[length];
        in.readFully(body);
        return body;
    }

    public static void main(String[] args) throws Exception {
        Driver driver = new Driver(args[0]);
        DataInputStream in = new DataInputStream(new BufferedInputStream(System.in));
        PrintStream out = System.out;
        for (byte[] body = frame(in); body != null; body = frame(in)) {
            String text = new String(body, StandardCharsets.UTF_8);
            try {
                long[] spent = driver.round(text);
                out.println("OK " + spent[0] + " " + spent[1]);
            } catch (InvocationTargetException e) {
                out.println("ERR " + describe(e.getCause()));
            } catch (Exception e) {
                out.println("ERR " + describe(e));
            }
            out.flush();
        }
    }

    /** One line naming a refusal — never a stack trace, which would break framing. */
    private static String describe(Throwable error) {
        if (error == null) {
            return "unknown";
        }
        String message = error.getMessage();
        return (error.getClass().getSimpleName() + ": "
                + (message == null ? "" : message)).replace('\n', ' ');
    }
}
